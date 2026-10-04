from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.core.validators import validate_email
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from common.demo_fakers import changed_values, contact_value_faker, fake_applicant_data, fake_user_data
from common.notifications import send_email_notification, send_telegram_notification
from common.rate_limit import is_rate_limited
from common.request import get_client_ip
from common.validators import validate_phone, validate_telegram_handle
from consultations.models import Consultation
from users.models import User


@override_settings(ADMIN_NOTIFICATION_EMAIL='admin@example.com', DEFAULT_FROM_EMAIL='noreply@example.com')
class SendEmailNotificationTests(SimpleTestCase):
    @patch('common.notifications.send_mail')
    def test_success_returns_true(self, mock_send_mail):
        result = send_email_notification('subject', 'message')

        self.assertTrue(result)
        mock_send_mail.assert_called_once()

    @patch('common.notifications.send_mail', side_effect=Exception('smtp down'))
    def test_smtp_failure_returns_false_instead_of_raising(self, mock_send_mail):
        result = send_email_notification('subject', 'message')

        self.assertFalse(result)

    @override_settings(ADMIN_NOTIFICATION_EMAIL='')
    @patch('common.notifications.send_mail')
    def test_missing_admin_email_returns_false_without_sending(self, mock_send_mail):
        result = send_email_notification('subject', 'message')

        self.assertFalse(result)
        mock_send_mail.assert_not_called()

    @patch('common.notifications.send_mail', side_effect=OSError('[Errno 101] Network is unreachable'))
    def test_failure_log_names_the_notification_but_not_its_body(self, mock_send_mail):
        # Тема (с именем клиента) в логе допустима - по ней видно, какое письмо не ушло, а
        # traceback показывает, на каком шаге упало соединение. Тело письма (контакт, текст) - нет.
        with self.assertLogs('common.notifications', level='ERROR') as logs:
            send_email_notification('Новая заявка от Иван Иванов', 'Телефон +79991234567')

        output = '\n'.join(logs.output)
        self.assertIn('Иван Иванов', output)
        self.assertIn('Errno 101', output)
        self.assertNotIn('+79991234567', output)
        self.assertIsNotNone(logs.records[0].exc_info)


@override_settings(TELEGRAM_BOT_TOKEN='test-token', TELEGRAM_ADMIN_CHAT_ID='123456')
class SendTelegramNotificationTests(SimpleTestCase):
    @patch('common.notifications.requests.post')
    def test_success_returns_true(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None

        result = send_telegram_notification('message')

        self.assertTrue(result)
        mock_post.assert_called_once()

    @patch('common.notifications.requests.post', side_effect=requests.RequestException('network error'))
    def test_network_error_returns_false_instead_of_raising(self, mock_post):
        result = send_telegram_notification('message')

        self.assertFalse(result)

    @patch('common.notifications.requests.post')
    def test_http_error_log_has_reason_but_no_token_or_message(self, mock_post):
        # requests кладёт полный URL (с токеном бота) в текст HTTPError, а в
        # сообщении - данные клиента: ни то, ни другое не должно попасть в лог.
        # Причина (статус, "Unauthorized") остаётся, токен в ней замаскирован.
        response = Mock(status_code=401)
        mock_post.return_value.raise_for_status.side_effect = requests.HTTPError(
            '401 Client Error: Unauthorized for url: https://api.telegram.org/bottest-token/sendMessage',
            response=response,
        )

        with self.assertLogs('common.notifications', level='ERROR') as logs:
            result = send_telegram_notification('Имя: Иван Иванов\nСвязь: +79991234567')

        output = '\n'.join(logs.output)
        self.assertFalse(result)
        self.assertIn('401', output)
        self.assertIn('Unauthorized', output)
        self.assertIn('bot***/sendMessage', output)
        self.assertNotIn('test-token', output)
        self.assertNotIn('Иван Иванов', output)
        self.assertNotIn('+79991234567', output)
        self.assertIsNone(logs.records[0].exc_info)

    @patch('common.notifications.requests.post')
    def test_connection_error_log_has_reason_but_no_token(self, mock_post):
        # У ConnectionError/Timeout тоже URL в тексте (Max retries exceeded with url: /bot<token>/...).
        mock_post.side_effect = requests.ConnectionError(
            "HTTPSConnectionPool(host='api.telegram.org'): Max retries exceeded with url: /bottest-token/sendMessage",
        )

        with self.assertLogs('common.notifications', level='ERROR') as logs:
            send_telegram_notification('message')

        output = '\n'.join(logs.output)
        self.assertIn('Max retries exceeded', output)
        self.assertNotIn('test-token', output)

    @override_settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_ADMIN_CHAT_ID='')
    @patch('common.notifications.requests.post')
    def test_missing_credentials_returns_false_without_request(self, mock_post):
        result = send_telegram_notification('message')

        self.assertFalse(result)
        mock_post.assert_not_called()


class IsRateLimitedTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_first_call_is_not_limited(self):
        self.assertFalse(is_rate_limited('scope', 'sender', 3, 60))

    def test_calls_under_limit_are_not_limited(self):
        for _ in range(3):
            self.assertFalse(is_rate_limited('scope', 'sender', 3, 60))

    def test_call_at_limit_is_limited(self):
        for _ in range(3):
            is_rate_limited('scope', 'sender', 3, 60)

        self.assertTrue(is_rate_limited('scope', 'sender', 3, 60))

    @patch('common.rate_limit.cache.set', wraps=cache.set)
    def test_every_write_uses_the_full_window_not_the_cache_default_timeout(self, mock_set):
        # cache.incr() наследует BaseCache.incr(), который внутри делает set() БЕЗ
        # timeout — на бэкендах, не переопределяющих incr() (DatabaseCache и почти
        # все, кроме LocMemCache), это молча срезает TTL ключа до
        # CACHES['default']['TIMEOUT'] (300 секунд по умолчанию) вместо window_seconds.
        # Проверяем, что КАЖДАЯ запись явно проставляет полное окно.
        window_seconds = 3600
        for _ in range(3):
            is_rate_limited('scope', 'sender', 5, window_seconds)

        self.assertTrue(mock_set.call_args_list)
        for _, kwargs in mock_set.call_args_list:
            self.assertEqual(kwargs.get('timeout'), window_seconds)


class GetClientIpTests(SimpleTestCase):
    """
    За Caddy -> nginx -> gunicorn REMOTE_ADDR - адрес контейнера nginx, одинаковый
    для всех посетителей: без чтения X-Forwarded-For лимиты общие на весь сайт.

    TRUSTED_PROXY_HOPS=1 - наша инфраструктура дописывает в X-Forwarded-For
    ровно одно звено (nginx), так что доверенная длина цепочки - всегда 2:
    [то, что решил Caddy, IP контейнера Caddy]. Любая другая длина - сигнал,
    что цепочка не такая, как ожидалось, а не повод угадывать позицию.
    """

    def _request(self, **headers):
        return RequestFactory().get('/', REMOTE_ADDR='172.18.0.5', **headers)

    @override_settings(TRUSTED_PROXY_HOPS=1)
    def test_takes_entry_before_our_own_hops_when_length_matches(self):
        request = self._request(HTTP_X_FORWARDED_FOR='203.0.113.7, 172.18.0.2')

        self.assertEqual(get_client_ip(request), '203.0.113.7')

    @override_settings(TRUSTED_PROXY_HOPS=1)
    def test_falls_back_and_warns_when_chain_shorter_than_expected(self):
        # Например, кто-то обошёл nginx/Caddy и достучался до backend напрямую.
        request = self._request(HTTP_X_FORWARDED_FOR='203.0.113.7')

        with self.assertLogs('common.request', level='WARNING'):
            self.assertEqual(get_client_ip(request), '172.18.0.5')

    @override_settings(TRUSTED_PROXY_HOPS=1)
    def test_falls_back_and_warns_when_chain_longer_than_expected(self):
        # Например, добавили ещё один прокси (CDN) и забыли поднять TRUSTED_PROXY_HOPS.
        request = self._request(HTTP_X_FORWARDED_FOR='203.0.113.7, 198.51.100.1, 172.18.0.2')

        with self.assertLogs('common.request', level='WARNING'):
            self.assertEqual(get_client_ip(request), '172.18.0.5')

    @override_settings(TRUSTED_PROXY_HOPS=1)
    def test_falls_back_and_warns_without_forwarded_for(self):
        with self.assertLogs('common.request', level='WARNING'):
            self.assertEqual(get_client_ip(self._request()), '172.18.0.5')

    @override_settings(TRUSTED_PROXY_HOPS=0)
    def test_ignores_forwarded_for_when_no_trusted_hops(self):
        # Без прокси (локальная разработка) заголовок мог подставить сам клиент.
        request = self._request(HTTP_X_FORWARDED_FOR='203.0.113.7, 172.18.0.2')

        self.assertEqual(get_client_ip(request), '172.18.0.5')


class ContactValueFakerTests(SimpleTestCase):
    """
    Подмена контакта в демо-режиме. Значение обязано проходить те же проверки формата,
    что и реальный ввод: иначе при правке заявки форма не пропустит уже сохранённый
    (подменённый) контакт, и текст сообщения нельзя будет изменить, не меняя контакт.
    """

    VALIDATORS = {
        'phone': validate_phone,
        'whatsapp': validate_phone,
        'telegram': validate_telegram_handle,
        'email': validate_email,
    }

    def test_replacement_passes_the_same_validators_as_real_input(self):
        for method, validator in self.VALIDATORS.items():
            with self.subTest(method=method):
                for _ in range(300):
                    validator(contact_value_faker(method))

    def test_email_never_points_to_a_real_mailbox(self):
        # Reserved-домены example.* (RFC 2606): адрес не может принадлежать живому человеку.
        for _ in range(100):
            self.assertRegex(contact_value_faker('email'), r'@example\.(com|org|net)$')

    def test_phone_uses_unassigned_code_so_it_cannot_belong_to_a_subscriber(self):
        for _ in range(100):
            self.assertTrue(contact_value_faker('phone').startswith('+7000'))


class DemoModeNoticeTests(TestCase):
    """
    Пользователь должен узнать о подмене данных до того, как начнёт вводить их в формы:
    полоса на каждой странице и пояснение в каждой из четырёх форм с персональными данными.
    """

    BANNER = 'Демонстрационная версия'
    NOTE = 'Демо-режим.'

    def setUp(self):
        user = User.objects.create_user(
            username='notice_user', email='notice@example.com', password='pass12345',
            first_name='А', last_name='Б',
        )
        consultation = Consultation.objects.create(
            user=user, name='А', contact_method='phone', contact_value='+70000000000', message='м',
        )
        self.client.force_login(user)
        self.form_urls = {
            'заявка': '/consultation/',
            'правка заявки': f'/consultation/my/{consultation.pk}/edit/',
            'профиль': '/accounts/profile/',
        }

    @override_settings(DEMO_MODE=True)
    def test_banner_is_shown_on_every_page(self):
        for url in ('/', '/articles/', '/consultation/', '/accounts/profile/'):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), self.BANNER)

    @override_settings(DEMO_MODE=True)
    def test_note_is_shown_in_every_form_that_takes_personal_data(self):
        for name, url in self.form_urls.items():
            with self.subTest(form=name):
                self.assertContains(self.client.get(url), self.NOTE)

        # Регистрация доступна только анонимному пользователю.
        self.assertContains(Client().get('/accounts/register/'), self.NOTE)

    @override_settings(DEMO_MODE=False)
    def test_nothing_is_shown_when_demo_mode_is_off(self):
        for url in ('/', *self.form_urls.values()):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotContains(response, self.BANNER)
                self.assertNotContains(response, self.NOTE)
        self.assertNotContains(Client().get('/accounts/register/'), self.NOTE)


class DemoFakerCoreTests(SimpleTestCase):
    """
    Ядро подмены работает со словарями (validated_data сериализаторов, cleaned_data форм),
    а не с формами: так одна и та же логика обслуживает и сайт, и API.
    """

    def test_changed_values_on_create_counts_every_value_as_entered(self):
        self.assertEqual(changed_values({'a': 1, 'b': 2}), {'a': 1, 'b': 2})

    def test_changed_values_on_update_keeps_only_values_that_differ_from_the_instance(self):
        instance = SimpleNamespace(a=1, b=2)

        self.assertEqual(changed_values({'a': 1, 'b': 3}, instance), {'b': 3})

    def test_changed_values_treats_a_field_unknown_to_the_instance_as_changed(self):
        self.assertEqual(changed_values({'new': 1}, SimpleNamespace()), {'new': 1})

    def test_applicant_data_replaces_only_the_fields_that_were_entered(self):
        fakes = fake_applicant_data({'name': 'Иван'}, 'phone')

        self.assertEqual(set(fakes), {'name'})
        self.assertTrue(fakes['name'].endswith('faked'))

    def test_applicant_contact_follows_the_contact_method(self):
        def contact(method):
            return fake_applicant_data({'contact_value': 'x'}, method)['contact_value']

        self.assertRegex(contact('email'), r'@example\.(com|org|net)$')
        self.assertTrue(contact('telegram').startswith('@'))
        self.assertTrue(contact('phone').startswith('+7000'))

    def test_nothing_entered_means_nothing_replaced(self):
        self.assertEqual(fake_applicant_data({}, 'phone'), {})
        self.assertEqual(fake_user_data({}), {})

    def test_user_data_replaces_only_the_names_that_were_entered(self):
        fakes = fake_user_data({'first_name': 'Иван', 'email': 'real@mail.ru'})

        self.assertEqual(set(fakes), {'first_name'})
        self.assertTrue(fakes['first_name'].endswith('faked'))

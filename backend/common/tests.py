from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from common.notifications import send_email_notification, send_telegram_notification
from common.rate_limit import is_rate_limited
from common.request import get_client_ip


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

import time
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import Client, TestCase
from rest_framework import status
from rest_framework.test import APIClient

from common.constants import (
    CONSULTATION_CREATE_RATE_LIMIT,
    CONSULTATION_SESSION_CLAIM_KEY,
    CONSULTATION_SESSION_CLAIM_TTL_SECONDS,
)
from consultations.models import Consultation
from consultations.signals import _notify_and_mark_on_failure
from users.models import User

CONSULTATION_API_URL = '/api/v1/consultations/'
CONSULTATION_MY_API_URL = '/api/v1/consultations/my/'
CONSULTATION_FORM_URL = '/consultation/'
CONSULTATION_SUCCESS_URL = '/consultation/success/'
STAFF_PANEL_URL = '/consultation/staff/'

DEFAULT_CONTACT_VALUE = '+79991234567'
CONTACT_VALUE_FIELD = 'contact_value'
SPAM_HONEYPOT_VALUE = 'http://spam.example'
INVALID_PHONE_VALUE = 'not-a-phone'
INVALID_EMAIL_VALUE = 'not-an-email'
OWN_OPEN_CONSULTATION_MESSAGE_SUBSTRING = 'уже есть заявка'


class ThrottleCacheClearingTestCase(TestCase):
    """
    И ScopedRateThrottle на создании заявок, и is_rate_limited() в
    remember_anonymous_consultation хранят счётчики в django.core.cache, который
    не откатывается вместе с транзакцией TestCase — без явной очистки тесты в
    одном прогоне (default REMOTE_ADDR у django.test.Client один и тот же для
    всех) начинают друг другу мешать через общий лимит.
    """

    def setUp(self):
        super().setUp()
        cache.clear()


def _api_payload(**overrides):
    payload = {
        'name': 'Иван',
        'contact_method': 'phone',
        'contact_value': DEFAULT_CONTACT_VALUE,
        'message': 'Хочу записаться на консультацию.',
    }
    payload.update(overrides)
    return payload


def _form_payload(**overrides):
    payload = _api_payload()
    payload['privacy_consent'] = True
    payload['website'] = ''
    payload.update(overrides)
    return payload


def _create_user(username, **overrides):
    defaults = {'email': f'{username}@example.com', 'password': 'pass12345'}
    defaults.update(overrides)
    return User.objects.create_user(username=username, **defaults)


class ConsultationSquattingFixTests(ThrottleCacheClearingTestCase):
    """
    Раньше UniqueConstraint на (contact_method, contact_value) + "тихое слияние"
    дублей позволяли застолбить чужой контакт мусорной заявкой: настоящая заявка
    с тем же контактом молча проваливалась (аноним получал страницу успеха, но
    в базе оставалась только заявка атакующего). Теперь каждая отправка — всегда
    отдельная строка, ничего не может быть тихо отброшено.
    """

    def test_api_second_submission_with_same_contact_is_saved_separately(self):
        client = APIClient()
        first = client.post(CONSULTATION_API_URL, _api_payload(name='Атакующий', message='мусор'), format='json')
        second = client.post(
            CONSULTATION_API_URL, _api_payload(name='Мария', message='Срочно нужна помощь'), format='json',
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        saved = list(Consultation.objects.filter(contact_value=DEFAULT_CONTACT_VALUE).values_list('name', 'message'))
        self.assertEqual(len(saved), 2)
        self.assertIn(('Мария', 'Срочно нужна помощь'), saved)

    def test_form_second_submission_with_same_contact_is_saved_separately(self):
        attacker_client = Client()
        maria_client = Client()

        attacker_client.post(CONSULTATION_FORM_URL, _form_payload(name='Атакующий', message='мусор'))
        maria_resp = maria_client.post(
            CONSULTATION_FORM_URL, _form_payload(name='Мария', message='Срочно нужна помощь'),
        )

        self.assertRedirects(maria_resp, CONSULTATION_SUCCESS_URL)
        saved = list(Consultation.objects.filter(contact_value=DEFAULT_CONTACT_VALUE).values_list('name', 'message'))
        self.assertEqual(len(saved), 2)
        self.assertIn(('Мария', 'Срочно нужна помощь'), saved)

    def test_create_response_never_includes_read_only_fields(self):
        # Не связано напрямую со сквоттингом, но сериализатор для create по-прежнему
        # отдаёт только то, что прислал сам вызывающий — ни id, ни служебные поля.
        client = APIClient()
        resp = client.post(CONSULTATION_API_URL, _api_payload(), format='json')

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        for read_only_field in ('id', 'user', 'status', 'notification_failed', 'created_at'):
            self.assertNotIn(read_only_field, resp.data)


class ConsultationCreateRateLimitTests(ThrottleCacheClearingTestCase):
    """
    Без UniqueConstraint единственная защита от флуда — лимит на создание,
    привязанный к отправителю (IP/пользователю), а не к содержимому заявки.
    """

    def test_form_creation_is_throttled_per_sender_not_per_contact(self):
        client = Client()
        for i in range(CONSULTATION_CREATE_RATE_LIMIT):
            resp = client.post(CONSULTATION_FORM_URL, _form_payload(contact_value=f'+7999000000{i}'))
            self.assertRedirects(resp, CONSULTATION_SUCCESS_URL)

        over_limit_value = '+79990000099'
        client.post(CONSULTATION_FORM_URL, _form_payload(contact_value=over_limit_value))

        self.assertEqual(Consultation.objects.count(), CONSULTATION_CREATE_RATE_LIMIT)
        # Совершенно новый, ранее не встречавшийся контакт всё равно не спасает —
        # лимит именно на отправителя, не на contact_value.
        self.assertFalse(Consultation.objects.filter(contact_value=over_limit_value).exists())

    def test_api_creation_is_throttled_per_sender(self):
        client = APIClient()
        for i in range(CONSULTATION_CREATE_RATE_LIMIT):
            resp = client.post(CONSULTATION_API_URL, _api_payload(contact_value=f'+7999111000{i}'), format='json')
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        over_limit_resp = client.post(
            CONSULTATION_API_URL, _api_payload(contact_value='+79991110099'), format='json',
        )

        self.assertEqual(over_limit_resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_different_senders_are_not_limited_by_each_others_activity(self):
        # То самое отличие от лимита "по контакту": разные отправители с ОДНИМ и тем же
        # contact_value друг другу не мешают. Client() по умолчанию не меняет IP между
        # экземплярами, поэтому REMOTE_ADDR задаётся явно — иначе это был бы тот же
        # отправитель и тест совпадал бы с проверкой лимита выше, а не с её отсутствием
        # между разными отправителями.
        sender_count = CONSULTATION_CREATE_RATE_LIMIT + 3
        for i in range(sender_count):
            resp = Client().post(CONSULTATION_FORM_URL, _form_payload(), REMOTE_ADDR=f'10.0.0.{i}')
            self.assertRedirects(resp, CONSULTATION_SUCCESS_URL)

        self.assertEqual(Consultation.objects.filter(contact_value=DEFAULT_CONTACT_VALUE).count(), sender_count)


class ConsultationOwnOpenConsultationMessageTests(ThrottleCacheClearingTestCase):
    def test_authenticated_user_gets_informed_about_own_open_consultation(self):
        user = User.objects.create_user(username='client1', email='client1@example.com', password='pass12345')
        Consultation.objects.create(
            user=user, name='Иван', contact_method='phone', contact_value='+79991111111',
            message='Первая заявка',
        )

        client = Client()
        client.force_login(user)
        response = client.post(
            CONSULTATION_FORM_URL,
            _form_payload(contact_method='email', contact_value='client1@example.com'),
            follow=True,
        )

        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any(OWN_OPEN_CONSULTATION_MESSAGE_SUBSTRING in m for m in messages))


class ConsultationHoneypotTests(ThrottleCacheClearingTestCase):
    def test_api_rejects_filled_honeypot(self):
        client = APIClient()
        resp = client.post(CONSULTATION_API_URL, _api_payload(website=SPAM_HONEYPOT_VALUE), format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Consultation.objects.count(), 0)

    def test_form_rejects_filled_honeypot(self):
        client = Client()
        resp = client.post(CONSULTATION_FORM_URL, _form_payload(website=SPAM_HONEYPOT_VALUE))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Consultation.objects.count(), 0)


class ConsultationContactValidationTests(ThrottleCacheClearingTestCase):
    """
    Consultation.clean() — единственное место с логикой валидации контакта,
    переиспользуемое и формой (через full_clean), и API-сериализатором.
    """

    def test_api_rejects_invalid_phone(self):
        client = APIClient()
        resp = client.post(CONSULTATION_API_URL, _api_payload(contact_value=INVALID_PHONE_VALUE), format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(CONTACT_VALUE_FIELD, resp.data)

    def test_api_rejects_invalid_email(self):
        client = APIClient()
        resp = client.post(
            CONSULTATION_API_URL,
            _api_payload(contact_method='email', contact_value=INVALID_EMAIL_VALUE),
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(CONTACT_VALUE_FIELD, resp.data)

    def test_form_rejects_invalid_phone(self):
        client = Client()
        resp = client.post(CONSULTATION_FORM_URL, _form_payload(contact_value=INVALID_PHONE_VALUE))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Consultation.objects.count(), 0)


class NotifyAndMarkOnFailureTests(TestCase):
    """
    _notify_and_mark_on_failure — то, что реально выполняется в фоновом потоке
    после post_save. Дергаем её напрямую как обычную функцию, а не через
    transaction.on_commit + threading.Thread: колбэки on_commit не срабатывают
    внутри TestCase (транзакция теста откатывается, а не коммитится), так что
    через сигнал эту ветку в принципе не проверить.
    """

    def setUp(self):
        self.consultation = Consultation.objects.create(
            name='Иван', contact_method='phone', contact_value='+79991234567', message='msg',
        )

    def test_flag_defaults_to_true_right_after_creation(self):
        # До того, как фоновый поток вообще успел стартовать (не то что завершиться),
        # заявка уже считается непровеленной — а не "ждём и притворяемся, что всё ок".
        self.assertTrue(self.consultation.notification_failed)

    @patch('consultations.signals.notify_admin_of_new_consultation', return_value=(True, False))
    def test_flag_reset_to_false_when_at_least_one_channel_succeeds(self, mock_notify):
        _notify_and_mark_on_failure(self.consultation.pk)

        self.consultation.refresh_from_db()
        self.assertFalse(self.consultation.notification_failed)

    @patch('consultations.signals.notify_admin_of_new_consultation', return_value=(False, False))
    def test_flag_stays_true_when_both_channels_fail(self, mock_notify):
        _notify_and_mark_on_failure(self.consultation.pk)

        self.consultation.refresh_from_db()
        self.assertTrue(self.consultation.notification_failed)

    @patch('consultations.signals.notify_admin_of_new_consultation')
    def test_deleted_consultation_is_silently_skipped(self, mock_notify):
        deleted_pk = self.consultation.pk
        self.consultation.delete()

        _notify_and_mark_on_failure(deleted_pk)

        mock_notify.assert_not_called()

    @patch('consultations.signals.notify_admin_of_new_consultation', return_value=(True, False))
    def test_db_connection_is_closed_after_background_work(self, mock_notify):
        with patch('consultations.signals.connection') as mock_connection:
            _notify_and_mark_on_failure(self.consultation.pk)

        mock_connection.close.assert_called_once()

    @patch('consultations.signals.notify_admin_of_new_consultation', side_effect=RuntimeError('boom'))
    def test_db_connection_is_closed_even_if_notification_raises(self, mock_notify):
        with patch('consultations.signals.connection') as mock_connection:
            with self.assertRaises(RuntimeError):
                _notify_and_mark_on_failure(self.consultation.pk)

        mock_connection.close.assert_called_once()


class ConsultationViewSetPermissionTests(TestCase):
    """
    get_permissions заявок содержит три разные ветки (create/my/остальное) —
    заявки видны только персоналу, потому что там ФИО и контакты клиентов.
    """

    def setUp(self):
        self.staff = _create_user('consultation_staff', is_staff=True)
        self.owner = _create_user('consultation_owner')
        self.other_user = _create_user('consultation_other')
        self.own_consultation = Consultation.objects.create(
            user=self.owner, name='Иван', contact_method='phone', contact_value='+79992222222', message='msg',
        )
        self.other_consultation = Consultation.objects.create(
            user=self.other_user, name='Пётр', contact_method='phone', contact_value='+79993333333', message='msg',
        )

    def test_anonymous_cannot_list(self):
        resp = APIClient().get(CONSULTATION_API_URL)

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_authenticated_user_cannot_list(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)

        resp = client.get(CONSULTATION_API_URL)

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_list(self):
        client = APIClient()
        client.force_authenticate(user=self.staff)

        resp = client.get(CONSULTATION_API_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_my_action_requires_authentication(self):
        resp = APIClient().get(CONSULTATION_MY_API_URL)

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_my_action_returns_only_own_consultations(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)

        resp = client.get(CONSULTATION_MY_API_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        returned_ids = [item['id'] for item in resp.data]
        self.assertIn(self.own_consultation.id, returned_ids)
        self.assertNotIn(self.other_consultation.id, returned_ids)

    def test_staff_can_update_status(self):
        client = APIClient()
        client.force_authenticate(user=self.staff)

        resp = client.patch(
            f'{CONSULTATION_API_URL}{self.own_consultation.id}/', {'status': 'in_progress'}, format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.own_consultation.refresh_from_db()
        self.assertEqual(self.own_consultation.status, 'in_progress')

    def test_owner_cannot_update_status_of_own_consultation(self):
        # В отличие от статей/комментариев, у заявок нет "владелец тоже может" —
        # статус меняет только персонал.
        client = APIClient()
        client.force_authenticate(user=self.owner)

        resp = client.patch(
            f'{CONSULTATION_API_URL}{self.own_consultation.id}/', {'status': 'closed'}, format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.own_consultation.refresh_from_db()
        self.assertNotEqual(self.own_consultation.status, 'closed')


class StaffPanelAccessTests(TestCase):
    def test_anonymous_gets_404(self):
        resp = Client().get(STAFF_PANEL_URL)

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_regular_authenticated_user_gets_404(self):
        user = _create_user('staff_panel_regular')
        client = Client()
        client.force_login(user)

        resp = client.get(STAFF_PANEL_URL)

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_gets_200(self):
        staff = _create_user('staff_panel_staff', is_staff=True)
        client = Client()
        client.force_login(staff)

        resp = client.get(STAFF_PANEL_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)


REGISTER_URL = '/accounts/register/'
LOGIN_URL = '/accounts/login/'
VALID_PASSWORD = 'Str0ngP@ssw0rd2026'


def _registration_payload(**overrides):
    payload = {
        'username': 'claimtestuser',
        'email': 'claimtestuser@example.com',
        'first_name': 'Иван',
        'last_name': 'Иванов',
        'password1': VALID_PASSWORD,
        'password2': VALID_PASSWORD,
        'privacy_consent': True,
    }
    payload.update(overrides)
    return payload


class SessionBasedConsultationClaimingTests(ThrottleCacheClearingTestCase):
    """
    Привязка анонимной заявки к новому/входящему в систему пользователю —
    только по id, запомненному в сессии в момент реального создания заявки.
    Привязка по email небезопасна (email никем не подтверждается при
    регистрации — кто угодно может вписать чужой), поэтому используется
    другой, гораздо более высокий барьер: тот же браузер/сессия.
    """

    def test_anonymous_form_submission_is_claimed_on_registration(self):
        client = Client()
        client.post(CONSULTATION_FORM_URL, _form_payload())
        consultation = Consultation.objects.get(contact_value=DEFAULT_CONTACT_VALUE)
        self.assertIsNone(consultation.user_id)

        client.post(REGISTER_URL, _registration_payload())

        consultation.refresh_from_db()
        self.assertEqual(consultation.user.username, 'claimtestuser')

    def test_anonymous_form_submission_is_claimed_on_login(self):
        existing_user = _create_user('existing_login_user')
        client = Client()
        client.post(CONSULTATION_FORM_URL, _form_payload())
        consultation = Consultation.objects.get(contact_value=DEFAULT_CONTACT_VALUE)

        client.post(LOGIN_URL, {'username': 'existing_login_user', 'password': 'pass12345'})

        consultation.refresh_from_db()
        self.assertEqual(consultation.user_id, existing_user.pk)

    def test_attacker_registering_does_not_claim_victims_consultation_despite_same_contact(self):
        # "Жертва" — реальный автор заявки.
        victim_client = Client()
        victim_client.post(CONSULTATION_FORM_URL, _form_payload())
        victim_consultation = Consultation.objects.get(contact_value=DEFAULT_CONTACT_VALUE, name='Иван')

        # "Атакующий" знает контакт жертвы и шлёт свою заявку с тем же телефоном — она
        # сохраняется отдельной строкой (см. ConsultationSquattingFixTests) и запоминается
        # только в СВОЕЙ сессии, поэтому регистрация атакующего привязывает только её.
        attacker_client = Client()
        attacker_client.post(CONSULTATION_FORM_URL, _form_payload(name='Атакующий', message='другое сообщение'))
        attacker_client.post(REGISTER_URL, _registration_payload(
            username='attacker', email='attacker@example.com',
        ))

        victim_consultation.refresh_from_db()
        self.assertIsNone(victim_consultation.user_id)

        attacker_consultation = Consultation.objects.get(contact_value=DEFAULT_CONTACT_VALUE, name='Атакующий')
        self.assertEqual(attacker_consultation.user.username, 'attacker')

    def test_different_session_registration_does_not_claim(self):
        Client().post(CONSULTATION_FORM_URL, _form_payload())
        consultation = Consultation.objects.get(contact_value=DEFAULT_CONTACT_VALUE)

        # Совсем не связанный с заявкой человек регистрируется в своей сессии.
        Client().post(REGISTER_URL, _registration_payload())

        consultation.refresh_from_db()
        self.assertIsNone(consultation.user_id)

    def test_api_anonymous_create_is_claimed_on_djoser_registration(self):
        client = APIClient()
        create_resp = client.post(CONSULTATION_API_URL, _api_payload(), format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        consultation = Consultation.objects.get(contact_value=DEFAULT_CONTACT_VALUE)

        client.post('/api/v1/users/', {
            'username': 'apiclaimuser', 'email': 'apiclaimuser@example.com',
            'first_name': 'А', 'last_name': 'Б', 'password': VALID_PASSWORD,
        }, format='json')

        consultation.refresh_from_db()
        self.assertEqual(consultation.user.username, 'apiclaimuser')

    def test_claimed_consultation_becomes_visible_via_my_action(self):
        client = Client()
        client.post(CONSULTATION_FORM_URL, _form_payload())
        client.post(REGISTER_URL, _registration_payload())
        user = User.objects.get(username='claimtestuser')

        api_client = APIClient()
        api_client.force_authenticate(user=user)
        resp = api_client.get(CONSULTATION_MY_API_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_stale_session_entry_beyond_ttl_is_not_claimed(self):
        # Обещано анониму на странице успеха: связывание работает, только если
        # зайти прямо сейчас, а не когда-нибудь в течение всего срока жизни cookie.
        client = Client()
        client.post(CONSULTATION_FORM_URL, _form_payload())
        consultation = Consultation.objects.get(contact_value=DEFAULT_CONTACT_VALUE)

        session = client.session
        stale_timestamp = time.time() - CONSULTATION_SESSION_CLAIM_TTL_SECONDS - 1
        session[CONSULTATION_SESSION_CLAIM_KEY] = [[consultation.pk, stale_timestamp]]
        session.save()

        client.post(REGISTER_URL, _registration_payload())

        consultation.refresh_from_db()
        self.assertIsNone(consultation.user_id)

    def test_fresh_session_entry_within_ttl_is_claimed(self):
        # Тот же сценарий, но запись ещё не устарела — контрольная проверка,
        # что предыдущий тест падает именно из-за TTL, а не из-за поломки формата.
        client = Client()
        client.post(CONSULTATION_FORM_URL, _form_payload())
        consultation = Consultation.objects.get(contact_value=DEFAULT_CONTACT_VALUE)

        session = client.session
        fresh_timestamp = time.time() - CONSULTATION_SESSION_CLAIM_TTL_SECONDS + 60
        session[CONSULTATION_SESSION_CLAIM_KEY] = [[consultation.pk, fresh_timestamp]]
        session.save()

        client.post(REGISTER_URL, _registration_payload())

        consultation.refresh_from_db()
        self.assertEqual(consultation.user.username, 'claimtestuser')

    def test_all_consultations_within_sender_limit_are_remembered_and_claimable(self):
        # remember_anonymous_consultation больше не лимитирует сама по себе — создание
        # уже ограничено по отправителю (CONSULTATION_CREATE_RATE_LIMIT), так что вызвать
        # её больше этого числа раз за отведённое окно физически нельзя.
        client = Client()
        consultation_ids = []
        for i in range(CONSULTATION_CREATE_RATE_LIMIT):
            client.post(CONSULTATION_FORM_URL, _form_payload(contact_value=f'+799900000{i}'))
            consultation_ids.append(Consultation.objects.get(contact_value=f'+799900000{i}').pk)

        client.post(REGISTER_URL, _registration_payload())

        linked_count = Consultation.objects.filter(pk__in=consultation_ids, user__isnull=False).count()
        self.assertEqual(linked_count, CONSULTATION_CREATE_RATE_LIMIT)



import shutil
import tempfile

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient

from users.models import User

REGISTER_URL = '/accounts/register/'
LOGIN_URL = '/accounts/login/'
PROFILE_URL = '/accounts/profile/'
AVATAR_API_URL = '/api/v1/users/me/avatar/'
PASSWORD_RESET_URL = '/accounts/password_reset/'
PASSWORD_RESET_DONE_URL = '/accounts/password_reset/done/'
PASSWORD_RESET_COMPLETE_URL = '/accounts/reset/done/'

VALID_PASSWORD = 'Str0ngP@ssw0rd2026'
# 1x1 прозрачный PNG.
BASE64_PNG = (
    'data:image/png;base64,'
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


def _registration_payload(**overrides):
    payload = {
        'username': 'newuser',
        'email': 'newuser@example.com',
        'first_name': 'Иван',
        'last_name': 'Иванов',
        'password1': VALID_PASSWORD,
        'password2': VALID_PASSWORD,
        'privacy_consent': True,
    }
    payload.update(overrides)
    return payload


class RegistrationTests(TestCase):
    def test_valid_registration_creates_user_and_logs_in(self):
        client = Client()
        resp = client.post(REGISTER_URL, _registration_payload())

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertTrue(User.objects.filter(username='newuser').exists())

        follow_resp = client.get(resp.url)
        self.assertTrue(follow_resp.wsgi_request.user.is_authenticated)

    def test_forbidden_username_is_rejected(self):
        client = Client()
        resp = client.post(REGISTER_URL, _registration_payload(username='me'))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(User.objects.filter(email='newuser@example.com').exists())

    def test_missing_privacy_consent_is_rejected(self):
        client = Client()
        resp = client.post(REGISTER_URL, _registration_payload(privacy_consent=False))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(
            username='existing', email='newuser@example.com', password=VALID_PASSWORD,
            first_name='А', last_name='Б',
        )
        client = Client()
        resp = client.post(REGISTER_URL, _registration_payload())

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(User.objects.filter(email='newuser@example.com').count(), 1)


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='logintest', email='logintest@example.com', password=VALID_PASSWORD,
            first_name='А', last_name='Б',
        )

    def test_correct_credentials_log_in(self):
        client = Client()
        resp = client.post(LOGIN_URL, {'username': 'logintest', 'password': VALID_PASSWORD})

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        follow_resp = client.get(resp.url)
        self.assertTrue(follow_resp.wsgi_request.user.is_authenticated)

    def test_wrong_password_is_rejected(self):
        client = Client()
        resp = client.post(LOGIN_URL, {'username': 'logintest', 'password': 'wrong-password'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.wsgi_request.user.is_authenticated)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='profiletest', email='profiletest@example.com', password=VALID_PASSWORD,
            first_name='Старое', last_name='Имя',
        )

    def test_anonymous_is_redirected_to_login(self):
        client = Client()
        resp = client.get(PROFILE_URL)

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn(LOGIN_URL, resp.url)

    def test_authenticated_user_can_update_profile(self):
        client = Client()
        client.force_login(self.user)

        resp = client.post(PROFILE_URL, {
            'first_name': 'Новое', 'last_name': 'Имя', 'email': self.user.email,
        })

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Новое')


class AvatarApiTests(TestCase):
    """
    ImageField пишет файл на диск в обход транзакции TestCase — без временного
    MEDIA_ROOT загруженные в тестах аватарки навсегда оседают в media/.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix='psyhelper_test_media_')
        cls._override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(
            username='avatartest', email='avatartest@example.com', password=VALID_PASSWORD,
            first_name='А', last_name='Б',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_can_set_avatar(self):
        resp = self.client.put(AVATAR_API_URL, {'avatar': BASE64_PNG}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(bool(self.user.avatar))

    def test_empty_avatar_is_rejected(self):
        resp = self.client.put(AVATAR_API_URL, {'avatar': ''}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_delete_avatar(self):
        self.client.put(AVATAR_API_URL, {'avatar': BASE64_PNG}, format='json')

        resp = self.client.delete(AVATAR_API_URL)

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.user.refresh_from_db()
        self.assertFalse(bool(self.user.avatar))

    def test_anonymous_cannot_set_avatar(self):
        anon_client = APIClient()
        resp = anon_client.put(AVATAR_API_URL, {'avatar': BASE64_PNG}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PasswordResetTests(TestCase):
    """
    EMAIL_BACKEND в .env указывает на реальный SMTP — PasswordResetView шлёт письмо
    синхронно, в отличие от уведомлений о заявках/комментариях (те идут фоновым
    потоком через on_commit, который в TestCase не срабатывает вообще). Без явного
    переопределения на locmem каждый прогон тестов слал бы настоящее письмо.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='reset_user', email='reset_user@example.com', password=VALID_PASSWORD,
            first_name='А', last_name='Б',
        )

    def test_form_renders(self):
        resp = Client().get(PASSWORD_RESET_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_login_page_links_to_password_reset(self):
        resp = Client().get(LOGIN_URL)

        self.assertContains(resp, PASSWORD_RESET_URL)

    def test_known_email_sends_reset_link(self):
        resp = Client().post(PASSWORD_RESET_URL, {'email': self.user.email})

        self.assertRedirects(resp, PASSWORD_RESET_DONE_URL)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.username, mail.outbox[0].body)
        self.assertIn('/accounts/reset/', mail.outbox[0].body)

    def test_unknown_email_gives_identical_response_without_sending_mail(self):
        # Не выдаёт, зарегистрирован ли email, — тот же редирект, что и для существующего.
        known_resp = Client().post(PASSWORD_RESET_URL, {'email': self.user.email})
        mail.outbox.clear()
        unknown_resp = Client().post(PASSWORD_RESET_URL, {'email': 'nobody@example.com'})

        self.assertEqual(known_resp.status_code, unknown_resp.status_code)
        self.assertEqual(known_resp.url, unknown_resp.url)
        self.assertEqual(len(mail.outbox), 0)

    def test_full_reset_flow_changes_password(self):
        client = Client()
        client.post(PASSWORD_RESET_URL, {'email': self.user.email})

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        # Первый GET по ссылке из письма подменяет токен в URL на 'set-password' и
        # кладёт настоящий токен в сессию (защита от утечки токена через Referer) —
        # без этого шага POST с новым паролем не пройдёт.
        redirect_resp = client.get(f'/accounts/reset/{uid}/{token}/')
        self.assertEqual(redirect_resp.status_code, status.HTTP_302_FOUND)

        form_resp = client.get(redirect_resp.url)
        self.assertEqual(form_resp.status_code, status.HTTP_200_OK)

        post_resp = client.post(redirect_resp.url, {
            'new_password1': 'AnotherStr0ngPass!', 'new_password2': 'AnotherStr0ngPass!',
        })

        self.assertRedirects(post_resp, PASSWORD_RESET_COMPLETE_URL)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('AnotherStr0ngPass!'))

    def test_invalid_token_is_rejected(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        client = Client()

        resp = client.get(f'/accounts/reset/{uid}/invalid-token/', follow=True)

        self.assertContains(resp, 'недействительна')
        self.assertTrue(self.user.check_password(VALID_PASSWORD))

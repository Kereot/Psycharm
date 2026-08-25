from unittest.mock import patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from common.notifications import send_email_notification, send_telegram_notification
from common.rate_limit import is_rate_limited


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

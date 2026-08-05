from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings

from common.notifications import send_email_notification, send_telegram_notification


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

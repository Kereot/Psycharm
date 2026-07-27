import logging

import requests
from django.conf import settings
from django.core.mail import send_mail

from common.constants import TELEGRAM_REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = 'https://api.telegram.org/bot{token}/sendMessage'


def send_email_notification(subject, message):
    if not settings.ADMIN_NOTIFICATION_EMAIL:
        logger.warning('ADMIN_NOTIFICATION_EMAIL не задан, email-уведомление не отправлено.')
        return False
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=(settings.ADMIN_NOTIFICATION_EMAIL,),
            fail_silently=False,
        )
    except Exception:
        logger.exception('Не удалось отправить email-уведомление: %s', subject)
        return False
    return True


def send_telegram_notification(message):
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_ADMIN_CHAT_ID
    if not token or not chat_id:
        logger.warning('TELEGRAM_BOT_TOKEN/TELEGRAM_ADMIN_CHAT_ID не заданы, Telegram-уведомление не отправлено.')
        return False
    try:
        response = requests.post(
            TELEGRAM_API_URL.format(token=token),
            json={'chat_id': chat_id, 'text': message},
            timeout=TELEGRAM_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception('Не удалось отправить Telegram-уведомление: %s', message)
        return False
    return True

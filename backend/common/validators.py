import re

from django.core.exceptions import ValidationError

from common.constants import FORBIDDEN_USERNAMES

USERNAME_PATTERN = re.compile(r'^[\w.@+-]+$')
PHONE_PATTERN = re.compile(r'^\+?\d{10,15}$')
TELEGRAM_HANDLE_PATTERN = re.compile(r'^@?[A-Za-z][A-Za-z0-9_]{4,31}$')


def validate_username(value):
    if not USERNAME_PATTERN.match(value):
        raise ValidationError(
            'Имя пользователя может содержать только буквы, цифры и символы @/./+/-/_',
            params={'value': value},
        )
    if value.lower() in FORBIDDEN_USERNAMES:
        raise ValidationError(
            f'Имя пользователя «{value}» использовать нельзя.',
            params={'value': value},
        )


def validate_phone(value):
    if not PHONE_PATTERN.match(value):
        raise ValidationError(
            'Введите номер телефона в формате +79991234567 (10–15 цифр).',
            params={'value': value},
        )


def validate_telegram_handle(value):
    if not TELEGRAM_HANDLE_PATTERN.match(value):
        raise ValidationError(
            'Введите корректный юзернейм Telegram, например @username (5–32 символа).',
            params={'value': value},
        )

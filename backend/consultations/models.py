from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models

from common.constants import (
    CONSULTATION_CHOICE_FIELD_MAX_LENGTH,
    CONSULTATION_CONTACT_VALUE_MAX_LENGTH,
    CONSULTATION_NAME_MAX_LENGTH,
    CONSULTATION_STATUS_CHOICES,
    CONSULTATION_STATUS_NEW,
    CONTACT_METHOD_CHOICES,
    CONTACT_METHOD_EMAIL,
    CONTACT_METHOD_PHONE,
    CONTACT_METHOD_TELEGRAM,
    CONTACT_METHOD_WHATSAPP,
)
from common.validators import validate_phone, validate_telegram_handle

CONTACT_VALIDATORS = {
    CONTACT_METHOD_PHONE: validate_phone,
    CONTACT_METHOD_EMAIL: validate_email,
    CONTACT_METHOD_TELEGRAM: validate_telegram_handle,
    CONTACT_METHOD_WHATSAPP: validate_phone,
}


class Consultation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='consultations',
        verbose_name='Пользователь',
    )
    name = models.CharField('Имя', max_length=CONSULTATION_NAME_MAX_LENGTH)
    contact_method = models.CharField(
        'Способ связи',
        max_length=CONSULTATION_CHOICE_FIELD_MAX_LENGTH,
        choices=CONTACT_METHOD_CHOICES,
    )
    contact_value = models.CharField(
        'Контакт',
        max_length=CONSULTATION_CONTACT_VALUE_MAX_LENGTH,
    )
    message = models.TextField('Сообщение')
    status = models.CharField(
        'Статус',
        max_length=CONSULTATION_CHOICE_FIELD_MAX_LENGTH,
        choices=CONSULTATION_STATUS_CHOICES,
        default=CONSULTATION_STATUS_NEW,
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)
    # Пока фоновый поток не подтвердил успех явным сбросом в False, заявка считается непроверенной.
    notification_failed = models.BooleanField('Проблема с уведомлением', default=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Заявка на консультацию'
        verbose_name_plural = 'Заявки на консультацию'

    def __str__(self):
        return f'{self.name} ({self.get_contact_method_display()}) — {self.get_status_display()}'

    def clean(self):
        validator = CONTACT_VALIDATORS.get(self.contact_method)
        if validator is None:
            return
        try:
            validator(self.contact_value)
        except ValidationError as error:
            raise ValidationError({'contact_value': error.messages})

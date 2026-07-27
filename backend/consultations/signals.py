from django.db.models.signals import post_save
from django.dispatch import receiver

from common.exceptions import NotificationDeliveryError
from consultations.models import Consultation
from consultations.notifications import notify_admin_of_new_consultation


@receiver(post_save, sender=Consultation)
def notify_admin_of_new_consultation_signal(sender, instance, created, **kwargs):
    if not created:
        return

    email_sent, telegram_sent = notify_admin_of_new_consultation(instance)

    if not email_sent and not telegram_sent:
        raise NotificationDeliveryError(
            f'Не удалось уведомить администратора о заявке #{instance.pk} ни по email, ни через Telegram.'
        )

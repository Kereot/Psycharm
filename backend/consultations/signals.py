import logging
import threading

from django.db import connection, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from consultations.models import Consultation
from consultations.notifications import notify_admin_of_consultation_update, notify_admin_of_new_consultation

logger = logging.getLogger(__name__)


def _notify_and_mark_on_failure(consultation_id):
    try:
        try:
            consultation = Consultation.objects.get(pk=consultation_id)
        except Consultation.DoesNotExist:
            return

        email_sent, telegram_sent = notify_admin_of_new_consultation(consultation)

        if email_sent or telegram_sent:
            Consultation.objects.filter(pk=consultation_id).update(notification_failed=False)
    finally:
        connection.close()


def _notify_of_update_and_mark_on_failure(consultation_id, old_contact_method, old_contact_value, old_message):
    try:
        try:
            consultation = Consultation.objects.get(pk=consultation_id)
        except Consultation.DoesNotExist:
            return

        email_sent, telegram_sent = notify_admin_of_consultation_update(
            consultation, old_contact_method, old_contact_value, old_message,
        )

        # Запись уже существует и notification_failed мог быть False от прошлого успеха — явно выставляем оба исхода.
        Consultation.objects.filter(pk=consultation_id).update(
            notification_failed=not (email_sent or telegram_sent),
        )
    finally:
        connection.close()


def dispatch_consultation_update_notification(consultation, old_contact_method, old_contact_value, old_message):
    transaction.on_commit(
        lambda: threading.Thread(
            target=_notify_of_update_and_mark_on_failure,
            args=(consultation.pk, old_contact_method, old_contact_value, old_message),
            daemon=True,
        ).start()
    )


@receiver(post_save, sender=Consultation)
def notify_admin_of_new_consultation_signal(sender, instance, created, **kwargs):
    if not created:
        return

    logger.info(
        'Новая заявка на консультацию id=%s способ связи=%s пользователь id=%s',
        instance.pk, instance.contact_method, instance.user_id,
    )

    transaction.on_commit(
        lambda: threading.Thread(
            target=_notify_and_mark_on_failure,
            args=(instance.pk,),
            daemon=True,
        ).start()
    )

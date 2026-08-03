import threading

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from consultations.models import Consultation
from consultations.notifications import notify_admin_of_new_consultation


def _notify_and_mark_on_failure(consultation_id):
    try:
        consultation = Consultation.objects.get(pk=consultation_id)
    except Consultation.DoesNotExist:
        return

    email_sent, telegram_sent = notify_admin_of_new_consultation(consultation)

    if not email_sent and not telegram_sent:
        Consultation.objects.filter(pk=consultation_id).update(notification_failed=True)


@receiver(post_save, sender=Consultation)
def notify_admin_of_new_consultation_signal(sender, instance, created, **kwargs):
    if not created:
        return

    transaction.on_commit(
        lambda: threading.Thread(
            target=_notify_and_mark_on_failure,
            args=(instance.pk,),
            daemon=True,
        ).start()
    )

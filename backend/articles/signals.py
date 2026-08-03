import threading

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from articles.models import Comment
from articles.notifications import notify_admin_of_new_comment


def _notify_in_background(comment_id):
    try:
        comment = Comment.objects.select_related('article', 'author').get(pk=comment_id)
    except Comment.DoesNotExist:
        return
    notify_admin_of_new_comment(comment)


@receiver(post_save, sender=Comment)
def notify_admin_of_new_comment_signal(sender, instance, created, **kwargs):
    if not created:
        return

    transaction.on_commit(
        lambda: threading.Thread(
            target=_notify_in_background,
            args=(instance.pk,),
            daemon=True,
        ).start()
    )

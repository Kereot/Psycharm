import logging
import threading

from django.db import connection, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from articles.models import Comment, Rating
from articles.notifications import notify_admin_of_new_comment

logger = logging.getLogger(__name__)


def _notify_in_background(comment_id):
    # Соединение открывается в thread-local этого потока и никогда не закроется
    # само — request_finished (на который завязан close_old_connections) в фоновом
    # потоке не срабатывает. На SQLite незаметно, на Postgres — растущее число сессий.
    try:
        try:
            comment = Comment.objects.select_related('article', 'author').get(pk=comment_id)
        except Comment.DoesNotExist:
            return
        notify_admin_of_new_comment(comment)
    finally:
        connection.close()


@receiver(post_save, sender=Comment)
def notify_admin_of_new_comment_signal(sender, instance, created, **kwargs):
    if not created:
        return

    logger.info(
        'Новый комментарий id=%s к статье id=%s от пользователя id=%s',
        instance.pk, instance.article_id, instance.author_id,
    )

    transaction.on_commit(
        lambda: threading.Thread(
            target=_notify_in_background,
            args=(instance.pk,),
            daemon=True,
        ).start()
    )


@receiver(post_save, sender=Rating)
def log_new_rating_signal(sender, instance, created, **kwargs):
    if not created:
        return

    logger.info(
        'Новая оценка id=%s статье id=%s: %s (пользователь id=%s)',
        instance.pk, instance.article_id, instance.value, instance.author_id,
    )

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from users.models import User

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def log_new_user_signal(sender, instance, created, **kwargs):
    if not created:
        return
    logger.info('Зарегистрирован новый пользователь id=%s username=%s', instance.pk, instance.username)

from django.db.models.signals import post_save
from django.dispatch import receiver

from articles.models import Comment
from articles.notifications import notify_admin_of_new_comment


@receiver(post_save, sender=Comment)
def notify_admin_of_new_comment_signal(sender, instance, created, **kwargs):
    if not created:
        return
    notify_admin_of_new_comment(instance)

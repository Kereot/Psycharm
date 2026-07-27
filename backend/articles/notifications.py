from common.notifications import send_email_notification, send_telegram_notification


def _format_message(comment):
    return (
        f'Новый комментарий к статье «{comment.article.title}»\n'
        f'Автор: {comment.author}\n\n'
        f'{comment.text}'
    )


def notify_admin_of_new_comment(comment):
    subject = f'Новый комментарий к статье «{comment.article.title}»'
    message = _format_message(comment)
    send_email_notification(subject, message)
    send_telegram_notification(message)

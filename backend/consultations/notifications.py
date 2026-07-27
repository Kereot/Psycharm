from common.notifications import send_email_notification, send_telegram_notification


def _format_message(consultation):
    return (
        f'Новая заявка на консультацию\n'
        f'Имя: {consultation.name}\n'
        f'Связь: {consultation.get_contact_method_display()}: {consultation.contact_value}\n\n'
        f'{consultation.message}'
    )


def notify_admin_of_new_consultation(consultation):
    subject = f'Новая заявка на консультацию от {consultation.name}'
    message = _format_message(consultation)
    email_sent = send_email_notification(subject, message)
    telegram_sent = send_telegram_notification(message)
    return email_sent, telegram_sent

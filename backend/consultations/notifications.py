from common.constants import CONTACT_METHOD_CHOICES
from common.notifications import send_email_notification, send_telegram_notification

CONTACT_METHOD_LABELS = dict(CONTACT_METHOD_CHOICES)


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


def _format_update_message(consultation, old_contact_method, old_contact_value, old_message):
    old_contact_label = CONTACT_METHOD_LABELS.get(old_contact_method, old_contact_method)
    return (
        f'Заявка на консультацию №{consultation.pk} изменена клиентом ({consultation.name})\n\n'
        f'Было:\n'
        f'Связь: {old_contact_label}: {old_contact_value}\n'
        f'{old_message}\n\n'
        f'Стало:\n'
        f'Связь: {consultation.get_contact_method_display()}: {consultation.contact_value}\n'
        f'{consultation.message}'
    )


def notify_admin_of_consultation_update(consultation, old_contact_method, old_contact_value, old_message):
    subject = f'Заявка на консультацию №{consultation.pk} изменена'
    message = _format_update_message(consultation, old_contact_method, old_contact_value, old_message)
    email_sent = send_email_notification(subject, message)
    telegram_sent = send_telegram_notification(message)
    return email_sent, telegram_sent

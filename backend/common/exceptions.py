from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError as DRFValidationError


# Оценки статей (ratings)
class DuplicateRatingError(DRFValidationError):
    default_detail = 'Вы уже оценили эту статью.'
    default_code = 'duplicate_rating'


# Заявки на консультацию (consultations)
class DuplicateConsultationError(DRFValidationError):
    default_detail = 'У вас уже есть открытая заявка с этим контактом.'
    default_code = 'duplicate_consultation'


class NotificationDeliveryError(Exception):
    """Ни одним из способов не удалось доставить уведомление админу."""


class ConsultationNotificationFailed(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        'Не удалось передать заявку администратору. '
        'Пожалуйста, свяжитесь с нами напрямую через контакты на сайте.'
    )
    default_code = 'notification_failed'

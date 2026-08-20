from rest_framework.exceptions import ValidationError as DRFValidationError

from common.constants import DUPLICATE_RATING_MESSAGE


class DuplicateRatingError(DRFValidationError):
    """Исключение при дублировании оценки статьи (ratings)"""

    default_detail = DUPLICATE_RATING_MESSAGE
    default_code = 'duplicate_rating'

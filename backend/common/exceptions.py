from rest_framework.exceptions import ValidationError as DRFValidationError

from common.constants import DUPLICATE_RATING_MESSAGE


# Оценки статей (ratings)
class DuplicateRatingError(DRFValidationError):
    default_detail = DUPLICATE_RATING_MESSAGE
    default_code = 'duplicate_rating'

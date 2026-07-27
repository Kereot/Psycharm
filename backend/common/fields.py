from drf_extra_fields.fields import Base64ImageField
from rest_framework import serializers


class NoBlankBase64ImageField(Base64ImageField):
    """Base64ImageField, где явно присланное '' или null — ошибка, а отсутствие поля — нет."""

    def run_validation(self, data=serializers.empty):
        if data in ('', None):
            raise serializers.ValidationError('Поле изображения не может быть пустым.')
        return super().run_validation(data)

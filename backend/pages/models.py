from django.db import models

from common.constants import (
    SERVICE_PRICE_DESCRIPTION_MAX_LENGTH,
    SERVICE_PRICE_TITLE_MAX_LENGTH,
    SERVICE_PRICE_VALUE_MAX_LENGTH,
)


class ServicePrice(models.Model):
    title = models.CharField('Название', max_length=SERVICE_PRICE_TITLE_MAX_LENGTH)
    description = models.CharField(
        'Краткое описание', max_length=SERVICE_PRICE_DESCRIPTION_MAX_LENGTH, blank=True,
    )
    price = models.CharField('Стоимость', max_length=SERVICE_PRICE_VALUE_MAX_LENGTH)
    duration = models.CharField('Длительность', max_length=SERVICE_PRICE_VALUE_MAX_LENGTH)

    class Meta:
        ordering = ('id',)
        verbose_name = 'Позиция прайса'
        verbose_name_plural = 'Прайс-лист'

    def __str__(self):
        return self.title

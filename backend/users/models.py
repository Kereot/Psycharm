from django.contrib.auth.models import AbstractUser
from django.db import models

from common.constants import USER_CHAR_FIELD_MAX_LENGTH, USER_EMAIL_FIELD_MAX_LENGTH
from common.validators import validate_username


class User(AbstractUser):
    email = models.EmailField(
        'Адрес электронной почты',
        unique=True,
        max_length=USER_EMAIL_FIELD_MAX_LENGTH,
    )
    username = models.CharField(
        'Уникальный юзернейм',
        max_length=USER_CHAR_FIELD_MAX_LENGTH,
        unique=True,
        validators=(validate_username,),
    )
    first_name = models.CharField(
        'Имя',
        max_length=USER_CHAR_FIELD_MAX_LENGTH,
    )
    last_name = models.CharField(
        'Фамилия',
        max_length=USER_CHAR_FIELD_MAX_LENGTH,
    )
    avatar = models.ImageField(
        upload_to='users/avatars/',
        blank=True,
        null=True,
        verbose_name='Аватар',
    )

    REQUIRED_FIELDS = ('email', 'first_name', 'last_name')

    class Meta:
        ordering = ('username',)
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return self.username

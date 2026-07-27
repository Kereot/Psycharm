from django.conf import settings
from django.db import models

from common.constants import (
    ARTICLE_SLUG_MAX_LENGTH,
    ARTICLE_TITLE_MAX_LENGTH,
    RATING_CHOICES,
    VISUAL_NAME_LIMIT,
)


class Article(models.Model):
    title = models.CharField('Заголовок', max_length=ARTICLE_TITLE_MAX_LENGTH)
    slug = models.SlugField('Идентификатор', max_length=ARTICLE_SLUG_MAX_LENGTH, unique=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='articles',
        verbose_name='Автор',
    )
    content = models.TextField('Текст статьи')
    image = models.ImageField(
        'Изображение',
        upload_to='articles/images/',
        blank=True,
        null=True,
    )
    is_published = models.BooleanField('Опубликовано', default=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Статья'
        verbose_name_plural = 'Статьи'

    def __str__(self):
        return self.title


class AbstractArticleRelation(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, verbose_name='Статья')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='Автор',
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        abstract = True
        default_related_name = '%(class)ss'
        ordering = ('-created_at',)


class Comment(AbstractArticleRelation):
    text = models.TextField('Текст комментария')

    class Meta(AbstractArticleRelation.Meta):
        verbose_name = 'Комментарий'
        verbose_name_plural = 'Комментарии'

    def __str__(self):
        return f'{self.author}: {self.text[:VISUAL_NAME_LIMIT]}'


class Rating(AbstractArticleRelation):
    value = models.PositiveSmallIntegerField('Оценка', choices=RATING_CHOICES)

    class Meta(AbstractArticleRelation.Meta):
        constraints = (
            models.UniqueConstraint(
                fields=('article', 'author'),
                name='unique_article_author_rating',
            ),
        )
        verbose_name = 'Оценка'
        verbose_name_plural = 'Оценки'

    def __str__(self):
        return f'{self.author}: {self.article} — {self.value}'

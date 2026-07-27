from django.contrib import admin
from django.db.models import Count

from articles.models import Article, Comment, Rating


class HasCommentsFilter(admin.SimpleListFilter):
    title = 'наличие комментариев'
    parameter_name = 'has_comments'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'С комментариями'),
            ('no', 'Без комментариев'),
        )

    def queryset(self, request, queryset):
        queryset = queryset.annotate(comments_count=Count('comments'))
        if self.value() == 'yes':
            return queryset.filter(comments_count__gt=0)
        if self.value() == 'no':
            return queryset.filter(comments_count=0)
        return queryset


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'is_published', 'created_at')
    list_select_related = ('author',)
    list_filter = ('is_published', 'created_at', HasCommentsFilter)
    search_fields = ('title', 'content')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('article', 'author', 'created_at')
    list_select_related = ('article', 'author')
    search_fields = ('text',)


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ('article', 'author', 'value', 'created_at')
    list_select_related = ('article', 'author')
    list_filter = ('value',)

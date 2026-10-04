from django.contrib import admin
from django.db.models import Count
from django.shortcuts import redirect
from django.utils.text import Truncator

from articles.models import Article, Comment, CommentSettings, Rating


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


COMMENT_PREVIEW_LENGTH = 80


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('text_preview', 'article', 'author', 'is_approved', 'created_at')
    list_select_related = ('article', 'author')
    list_filter = ('is_approved', 'created_at')
    search_fields = ('text',)
    actions = ('approve_comments', 'hide_comments')

    @admin.display(description='Комментарий')
    def text_preview(self, comment):
        return Truncator(comment.text).chars(COMMENT_PREVIEW_LENGTH)

    @admin.action(description='Одобрить выбранные комментарии')
    def approve_comments(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'Одобрено комментариев: {updated}.')

    @admin.action(description='Скрыть выбранные комментарии (вернуть на модерацию)')
    def hide_comments(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f'Возвращено на модерацию: {updated}.')


@admin.register(CommentSettings)
class CommentSettingsAdmin(admin.ModelAdmin):

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect('admin:articles_commentsettings_change', CommentSettings.load().pk)


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ('article', 'author', 'value', 'created_at')
    list_select_related = ('article', 'author')
    list_filter = ('value',)

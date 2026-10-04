from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import Client, TestCase
from rest_framework import status
from rest_framework.test import APIClient

from articles.models import Article, Comment, CommentSettings, Rating
from articles.notifications import notify_admin_of_new_comment
from articles.signals import _notify_in_background
from common.constants import (
    ARTICLE_LIST_PAGE_SIZE,
    ARTICLE_PENDING_FORM_SESSION_KEY,
    COMMENT_CREATE_RATE_LIMIT,
    FORM_SESSION_WRITE_RATE_LIMIT,
)
from users.models import User

TYPED_COMMENT_TEXT = 'мой комментарий'
LOGIN_URL_SUBSTRING = 'login'


def _create_user(username, **overrides):
    defaults = {'email': f'{username}@example.com', 'password': 'pass12345'}
    defaults.update(overrides)
    return User.objects.create_user(username=username, **defaults)


def _create_article(author, slug='test-article', is_published=True):
    return Article.objects.create(
        title='Test article', slug=slug, content='content', is_published=is_published, author=author,
    )


class RatingDuplicateTests(TestCase):
    """
    Единственный слой обработки дубля — UniqueConstraint модели + except
    IntegrityError во вьюсете (без предварительной проверки в сериализаторе).
    """

    def test_duplicate_rating_returns_400_not_500(self):
        author = _create_user('author1')
        user = _create_user('rater1')
        article = _create_article(author)
        client = APIClient()
        client.force_authenticate(user=user)
        url = f'/api/v1/articles/{article.slug}/ratings/'

        first = client.post(url, {'value': 5}, format='json')
        second = client.post(url, {'value': 3}, format='json')

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Rating.objects.filter(article=article, author=user).count(), 1)

    def test_can_update_own_rating(self):
        author = _create_user('author2')
        user = _create_user('rater2')
        article = _create_article(author, slug='test-article-2')
        client = APIClient()
        client.force_authenticate(user=user)
        url = f'/api/v1/articles/{article.slug}/ratings/'

        create_resp = client.post(url, {'value': 2}, format='json')
        rating_id = create_resp.data['id']
        patch_resp = client.patch(f'{url}{rating_id}/', {'value': 5}, format='json')

        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Rating.objects.get(pk=rating_id).value, 5)


class UnpublishedArticleVisibilityTests(TestCase):
    def test_anonymous_cannot_see_unpublished_article(self):
        author = _create_user('author3')
        _create_article(author, slug='unpublished-1', is_published=False)
        client = APIClient()

        list_resp = client.get('/api/v1/articles/')
        detail_resp = client.get('/api/v1/articles/unpublished-1/')

        self.assertEqual(list_resp.data['count'], 0)
        self.assertEqual(detail_resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_can_see_unpublished_article(self):
        author = _create_user('author4')
        staff = _create_user('staff1', is_staff=True)
        _create_article(author, slug='unpublished-2', is_published=False)
        client = APIClient()
        client.force_authenticate(user=staff)

        list_resp = client.get('/api/v1/articles/')
        detail_resp = client.get('/api/v1/articles/unpublished-2/')

        self.assertEqual(list_resp.data['count'], 1)
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)

    def test_anonymous_cannot_comment_on_unpublished_article_via_api(self):
        # IsOwnerOrAdminOrReadOnly режет анонимный POST на уровне has_permission
        # раньше, чем вьюсет вообще посмотрит на article_slug — поэтому 401,
        # а не 404: для опубликованной статьи POST от анонима тоже даст 401,
        # так что различить существование статьи по коду ответа нельзя.
        author = _create_user('author5')
        _create_article(author, slug='unpublished-3', is_published=False)
        client = APIClient()

        resp = client.post('/api/v1/articles/unpublished-3/comments/', {'text': 'hi'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class LostCommentRecoveryTests(TestCase):
    """
    Анонимный POST на страницу статьи редиректит на логин; введённый текст
    должен восстанавливаться после входа, а не теряться.

    is_rate_limited() в article_detail хранит счётчик в django.core.cache,
    который не откатывается вместе с транзакцией TestCase — без явной очистки
    тесты в одном прогоне (default REMOTE_ADDR у django.test.Client один и тот
    же для всех) начинают друг другу мешать через общий лимит.
    """

    def setUp(self):
        cache.clear()

    def test_typed_comment_survives_login_redirect(self):
        author = _create_user('author6')
        article = _create_article(author, slug='recovery-article')
        client = Client()
        url = f'/articles/{article.slug}/'

        anon_resp = client.post(url, {'submit_comment': '1', 'text': TYPED_COMMENT_TEXT})
        self.assertEqual(anon_resp.status_code, status.HTTP_302_FOUND)
        self.assertIn(LOGIN_URL_SUBSTRING, anon_resp.url)

        user = _create_user('commenter1')
        client.force_login(user)
        get_resp = client.get(url)

        self.assertContains(get_resp, TYPED_COMMENT_TEXT)
        self.assertFalse(Comment.objects.filter(article=article, text=TYPED_COMMENT_TEXT).exists())

    def test_pending_stash_is_rate_limited_per_ip(self):
        author = _create_user('rate_limit_author')
        limit = FORM_SESSION_WRITE_RATE_LIMIT
        articles = [_create_article(author, slug=f'rate-limit-article-{i}') for i in range(limit + 1)]
        client = Client()

        for article in articles[:limit]:
            client.post(f'/articles/{article.slug}/', {'submit_comment': '1', 'text': 'text'})

        last_allowed_slug = client.session[ARTICLE_PENDING_FORM_SESSION_KEY]['slug']
        self.assertEqual(last_allowed_slug, articles[limit - 1].slug)

        over_limit_article = articles[limit]
        client.post(f'/articles/{over_limit_article.slug}/', {'submit_comment': '1', 'text': 'over limit'})

        # Попытка сверх лимита не должна была перезаписать сессию.
        self.assertEqual(client.session[ARTICLE_PENDING_FORM_SESSION_KEY]['slug'], last_allowed_slug)


class ArticleListViewTests(TestCase):
    def test_only_published_articles_are_listed(self):
        author = _create_user('list_author')
        _create_article(author, slug='published-list', is_published=True)
        _create_article(author, slug='unpublished-list', is_published=False)

        resp = Client().get('/articles/')

        slugs = [article.slug for article in resp.context['articles']]
        self.assertIn('published-list', slugs)
        self.assertNotIn('unpublished-list', slugs)

    def test_pagination_splits_articles_across_pages(self):
        author = _create_user('page_author')
        extra_articles = 5
        for i in range(ARTICLE_LIST_PAGE_SIZE + extra_articles):
            _create_article(author, slug=f'page-article-{i}', is_published=True)

        first_page = Client().get('/articles/')
        second_page = Client().get('/articles/', {'page': 2})

        self.assertEqual(len(first_page.context['articles']), ARTICLE_LIST_PAGE_SIZE)
        self.assertTrue(first_page.context['is_paginated'])
        self.assertEqual(len(second_page.context['articles']), extra_articles)

    def test_invalid_page_returns_404(self):
        resp = Client().get('/articles/', {'page': 999})

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class NotifyInBackgroundTests(TestCase):
    """
    _notify_in_background — то, что реально выполняется в фоновом потоке после
    post_save. on_commit-колбэки не срабатывают внутри TestCase (транзакция
    теста откатывается, а не коммитится), поэтому дёргаем функцию напрямую.
    """

    def setUp(self):
        self.author = _create_user('notify_author')
        self.article = _create_article(self.author, slug='notify-article')
        self.comment = Comment.objects.create(article=self.article, author=self.author, text='hello')

    @patch('articles.signals.notify_admin_of_new_comment')
    def test_notifies_about_the_created_comment(self, mock_notify):
        _notify_in_background(self.comment.pk)

        mock_notify.assert_called_once()
        notified_comment = mock_notify.call_args[0][0]
        self.assertEqual(notified_comment.pk, self.comment.pk)

    @patch('articles.signals.notify_admin_of_new_comment')
    def test_deleted_comment_is_silently_skipped(self, mock_notify):
        deleted_pk = self.comment.pk
        self.comment.delete()

        _notify_in_background(deleted_pk)

        mock_notify.assert_not_called()

    @patch('articles.signals.notify_admin_of_new_comment')
    def test_db_connection_is_closed_after_background_work(self, mock_notify):
        with patch('articles.signals.connection') as mock_connection:
            _notify_in_background(self.comment.pk)

        mock_connection.close.assert_called_once()

    @patch('articles.signals.notify_admin_of_new_comment', side_effect=RuntimeError('boom'))
    def test_db_connection_is_closed_even_if_notification_raises(self, mock_notify):
        with patch('articles.signals.connection') as mock_connection:
            with self.assertRaises(RuntimeError):
                _notify_in_background(self.comment.pk)

        mock_connection.close.assert_called_once()


class CommentCreateFormThrottleTests(TestCase):
    """
    Тот же лимит, что и в API (CommentCreateThrottleTests в api/tests.py), но для
    сайтовой формы, куда DRF ScopedRateThrottle не дотягивается вовсе.
    """

    def setUp(self):
        cache.clear()
        self.author = _create_user('form_throttle_author')
        self.article = _create_article(self.author, slug='form-throttle-article')
        self.user = _create_user('form_throttle_commenter')
        self.client = Client()
        self.client.force_login(self.user)

    def test_comment_creation_is_throttled(self):
        url = f'/articles/{self.article.slug}/'
        for _ in range(COMMENT_CREATE_RATE_LIMIT):
            self.client.post(url, {'submit_comment': '1', 'text': 'hi'})

        self.assertEqual(Comment.objects.filter(article=self.article).count(), COMMENT_CREATE_RATE_LIMIT)

        self.client.post(url, {'submit_comment': '1', 'text': 'one too many'})

        self.assertEqual(Comment.objects.filter(article=self.article).count(), COMMENT_CREATE_RATE_LIMIT)


def _set_premoderation(enabled):
    settings_row = CommentSettings.load()
    settings_row.premoderation_enabled = enabled
    settings_row.save()


class CommentSettingsTests(TestCase):
    """Единственная строка настроек, которую администратор переключает в админке."""

    def test_load_creates_the_row_with_premoderation_off(self):
        loaded = CommentSettings.load()

        self.assertEqual(loaded.pk, 1)
        self.assertFalse(loaded.premoderation_enabled)

    def test_there_is_only_ever_one_row(self):
        CommentSettings.load()
        CommentSettings(premoderation_enabled=True).save()

        self.assertEqual(CommentSettings.objects.count(), 1)
        self.assertTrue(CommentSettings.load().premoderation_enabled)

    def test_requirement_depends_on_the_switch_and_on_the_author_being_staff(self):
        regular = _create_user('mod_regular')
        staff = _create_user('mod_staff', is_staff=True)

        self.assertFalse(CommentSettings.requires_moderation(regular))

        _set_premoderation(True)

        self.assertTrue(CommentSettings.requires_moderation(regular))
        self.assertFalse(CommentSettings.requires_moderation(staff))


class CommentVisibilityTests(TestCase):
    def setUp(self):
        self.author = _create_user('vis_author')
        self.article = _create_article(self.author, slug='visibility-article')
        self.commenter = _create_user('vis_commenter')
        self.other = _create_user('vis_other')
        self.staff = _create_user('vis_staff', is_staff=True)
        self.approved = Comment.objects.create(article=self.article, author=self.other, text='одобренный')
        self.pending = Comment.objects.create(
            article=self.article, author=self.commenter, text='ожидающий', is_approved=False,
        )

    def _visible_to(self, user):
        return set(self.article.comments.visible_to(user))

    def test_comment_is_approved_by_default(self):
        # Старые комментарии (до появления поля) и созданные в админке не должны пропасть с сайта.
        self.assertTrue(Comment.objects.create(article=self.article, author=self.other, text='x').is_approved)

    def test_anonymous_sees_only_approved(self):
        self.assertEqual(self._visible_to(AnonymousUser()), {self.approved})

    def test_author_sees_own_pending_but_not_other_peoples(self):
        self.assertEqual(self._visible_to(self.commenter), {self.approved, self.pending})
        self.assertEqual(self._visible_to(self.other), {self.approved})

    def test_staff_sees_everything(self):
        self.assertEqual(self._visible_to(self.staff), {self.approved, self.pending})


class CommentPremoderationFormTests(TestCase):
    """Сайтовая форма комментария: при включённой премодерации комментарий ждёт одобрения."""

    def setUp(self):
        cache.clear()
        self.article_author = _create_user('pm_article_author')
        self.article = _create_article(self.article_author, slug='premoderation-article')
        self.url = f'/articles/{self.article.slug}/'
        self.commenter = _create_user('pm_commenter')
        self.other = _create_user('pm_other')
        self.staff = _create_user('pm_staff', is_staff=True)

    def _post_comment(self, user, text='Секретный комментарий'):
        client = Client()
        client.force_login(user)
        return client.post(self.url, {'submit_comment': '1', 'text': text}, follow=True)

    def _page_as(self, user=None):
        client = Client()
        if user is not None:
            client.force_login(user)
        return client.get(self.url)

    def test_premoderation_off_publishes_immediately(self):
        resp = self._post_comment(self.commenter)

        self.assertTrue(Comment.objects.get().is_approved)
        self.assertContains(self._page_as(), 'Секретный комментарий')
        self.assertContains(resp, 'Комментарий добавлен.')

    def test_premoderation_on_holds_the_comment_back(self):
        _set_premoderation(True)

        resp = self._post_comment(self.commenter)

        self.assertFalse(Comment.objects.get().is_approved)
        self.assertContains(resp, 'на модерацию')

    def test_pending_comment_is_hidden_from_anonymous_and_other_users(self):
        _set_premoderation(True)
        self._post_comment(self.commenter)

        self.assertNotContains(self._page_as(), 'Секретный комментарий')
        self.assertNotContains(self._page_as(self.other), 'Секретный комментарий')

    def test_pending_comment_is_visible_to_its_author_with_a_label(self):
        _set_premoderation(True)
        self._post_comment(self.commenter)

        page = self._page_as(self.commenter)

        self.assertContains(page, 'Секретный комментарий')
        self.assertContains(page, 'Ожидает модерации')

    def test_comment_counter_does_not_count_hidden_comments(self):
        _set_premoderation(True)
        self._post_comment(self.commenter)

        self.assertContains(self._page_as(), 'Комментарии (0)')

    def test_staff_comment_is_published_immediately(self):
        _set_premoderation(True)

        self._post_comment(self.staff)

        self.assertTrue(Comment.objects.get().is_approved)

    def test_settings_are_read_only_for_a_valid_submission(self):
        # requires_moderation() ходит в БД (CommentSettings.load): на пустом тексте, который всё
        # равно отклонит форма, этот запрос лишний.
        with patch.object(CommentSettings, 'requires_moderation', return_value=False) as requires_moderation:
            self._post_comment(self.commenter, text='')
            requires_moderation.assert_not_called()

            self._post_comment(self.commenter, text='нормальный текст')
            requires_moderation.assert_called_once()

    def test_turning_premoderation_off_does_not_approve_what_is_already_pending(self):
        _set_premoderation(True)
        self._post_comment(self.commenter)

        _set_premoderation(False)

        self.assertFalse(Comment.objects.get().is_approved)
        self.assertNotContains(self._page_as(), 'Секретный комментарий')


class CommentNotificationTests(TestCase):
    def setUp(self):
        self.author = _create_user('notif_author')
        self.article = _create_article(self.author, slug='notification-article')

    def _notify(self, **comment_fields):
        comment = Comment.objects.create(article=self.article, author=self.author, text='привет', **comment_fields)
        with patch('articles.notifications.send_email_notification') as email, \
                patch('articles.notifications.send_telegram_notification') as telegram:
            notify_admin_of_new_comment(comment)
        return email.call_args[0], telegram.call_args[0][0]

    def test_pending_comment_is_marked_in_both_channels(self):
        (subject, body), telegram_message = self._notify(is_approved=False)

        self.assertIn('на модерации', subject)
        self.assertIn('ожидает модерации', body)
        self.assertIn('ожидает модерации', telegram_message)

    def test_approved_comment_is_not_marked(self):
        (subject, body), telegram_message = self._notify()

        self.assertNotIn('модерации', subject)
        self.assertNotIn('модерации', body)
        self.assertNotIn('модерации', telegram_message)


class CommentModerationAdminTests(TestCase):
    def setUp(self):
        self.admin = _create_user('mod_admin', is_staff=True, is_superuser=True)
        self.client = Client()
        self.client.force_login(self.admin)
        author = _create_user('mod_admin_author')
        article = _create_article(author, slug='admin-moderation-article')
        self.pending = Comment.objects.create(article=article, author=author, text='ожидающий', is_approved=False)
        self.approved = Comment.objects.create(article=article, author=author, text='одобренный')

    def test_filter_shows_only_comments_awaiting_moderation(self):
        resp = self.client.get('/admin/articles/comment/?is_approved__exact=0')

        self.assertContains(resp, 'ожидающий')
        self.assertNotContains(resp, 'одобренный')

    def test_approve_action_publishes_selected_comments(self):
        self.client.post('/admin/articles/comment/', {
            'action': 'approve_comments', '_selected_action': [self.pending.pk],
        })

        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_approved)

    def test_hide_action_returns_selected_comments_to_moderation(self):
        self.client.post('/admin/articles/comment/', {
            'action': 'hide_comments', '_selected_action': [self.approved.pk],
        })

        self.approved.refresh_from_db()
        self.assertFalse(self.approved.is_approved)

    def test_settings_list_leads_straight_to_the_only_settings_form(self):
        resp = self.client.get('/admin/articles/commentsettings/', follow=True)

        self.assertEqual(resp.redirect_chain[0][0], '/admin/articles/commentsettings/1/change/')
        self.assertContains(resp, 'name="premoderation_enabled"')

    def test_administrator_can_switch_premoderation_on_and_off(self):
        url = '/admin/articles/commentsettings/1/change/'
        CommentSettings.load()

        self.client.post(url, {'premoderation_enabled': 'on', '_save': 'Сохранить'})
        self.assertTrue(CommentSettings.load().premoderation_enabled)

        self.client.post(url, {'_save': 'Сохранить'})
        self.assertFalse(CommentSettings.load().premoderation_enabled)

    def test_settings_row_cannot_be_added_or_deleted_from_admin(self):
        CommentSettings.load()

        self.assertEqual(self.client.get('/admin/articles/commentsettings/add/').status_code, 403)
        self.assertEqual(self.client.get('/admin/articles/commentsettings/1/delete/').status_code, 403)

from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase
from rest_framework import status
from rest_framework.test import APIClient

from articles.models import Article, Comment, Rating
from articles.signals import _notify_in_background
from common.constants import ARTICLE_LIST_PAGE_SIZE, ARTICLE_PENDING_FORM_SESSION_KEY, FORM_SESSION_WRITE_RATE_LIMIT
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

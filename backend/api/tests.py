from django.core.cache import cache
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from articles.models import Article, Comment, CommentSettings
from common.constants import COMMENT_CREATE_RATE_LIMIT
from pages.models import ServicePrice
from users.models import User

PRICES_URL = '/api/v1/prices/'
NEW_PRICE_PAYLOAD = {'title': 'Новая', 'price': '1000', 'duration': '30 мин'}
ORIGINAL_COMMENT_TEXT = 'original'


def _create_user(username, **overrides):
    defaults = {'email': f'{username}@example.com', 'password': 'pass12345'}
    defaults.update(overrides)
    return User.objects.create_user(username=username, **defaults)


class IsAdminOrReadOnlyTests(TestCase):
    def test_anonymous_can_read_but_not_create_price(self):
        ServicePrice.objects.create(title='Консультация', price='2000 руб.', duration='50 мин')
        client = APIClient()

        list_resp = client.get(PRICES_URL)
        create_resp = client.post(PRICES_URL, NEW_PRICE_PAYLOAD, format='json')

        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertIn(create_resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_staff_can_create_price(self):
        staff = _create_user('staff_price', is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff)

        resp = client.post(PRICES_URL, NEW_PRICE_PAYLOAD, format='json')

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_authenticated_non_staff_cannot_create_price(self):
        user = _create_user('regular_user')
        client = APIClient()
        client.force_authenticate(user=user)

        resp = client.post(PRICES_URL, NEW_PRICE_PAYLOAD, format='json')

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class IsOwnerOrAdminOrReadOnlyTests(TestCase):
    def setUp(self):
        self.author = _create_user('article_author')
        self.article = Article.objects.create(
            title='Test', slug='owner-test-article', content='content', author=self.author,
        )
        self.owner = _create_user('comment_owner')
        self.other = _create_user('comment_other')
        self.staff = _create_user('comment_staff', is_staff=True)
        self.comment = Comment.objects.create(article=self.article, author=self.owner, text=ORIGINAL_COMMENT_TEXT)

    def _comment_url(self):
        return f'/api/v1/articles/{self.article.slug}/comments/{self.comment.id}/'

    def _comments_list_url(self):
        return f'/api/v1/articles/{self.article.slug}/comments/'

    def test_owner_can_edit_own_comment(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)

        resp = client.patch(self._comment_url(), {'text': 'edited'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_other_authenticated_user_cannot_edit_someone_elses_comment(self):
        client = APIClient()
        client.force_authenticate(user=self.other)

        resp = client.patch(self._comment_url(), {'text': 'hijacked'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.text, ORIGINAL_COMMENT_TEXT)

    def test_staff_can_edit_any_comment(self):
        client = APIClient()
        client.force_authenticate(user=self.staff)

        resp = client.patch(self._comment_url(), {'text': 'moderated'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_anonymous_can_read_but_not_create_comment(self):
        client = APIClient()

        list_resp = client.get(self._comments_list_url())
        create_resp = client.post(self._comments_list_url(), {'text': 'spam'}, format='json')

        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertIn(create_resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class CommentCreateThrottleTests(TestCase):
    """
    Каждый комментарий поднимает фоновый поток с SMTP+Telegram (articles/signals.py) —
    без лимита залогиненный пользователь мог бы в цикле породить сколько угодно потоков.
    ScopedRateThrottle хранит счётчик в django.core.cache, который не откатывается вместе
    с транзакцией TestCase — без явной очистки тесты начинают друг другу мешать.
    """

    def setUp(self):
        cache.clear()
        self.author = _create_user('throttle_article_author')
        self.article = Article.objects.create(
            title='Test', slug='throttle-test-article', content='content', author=self.author,
        )
        self.user = _create_user('throttle_commenter')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _comments_list_url(self):
        return f'/api/v1/articles/{self.article.slug}/comments/'

    def test_comment_creation_is_throttled(self):
        for _ in range(COMMENT_CREATE_RATE_LIMIT):
            resp = self.client.post(self._comments_list_url(), {'text': 'hi'}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        over_limit_resp = self.client.post(self._comments_list_url(), {'text': 'one too many'}, format='json')

        self.assertEqual(over_limit_resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(Comment.objects.filter(article=self.article).count(), COMMENT_CREATE_RATE_LIMIT)


def _set_premoderation(enabled):
    settings_row = CommentSettings.load()
    settings_row.premoderation_enabled = enabled
    settings_row.save()


class CommentPremoderationApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.article_author = _create_user('api_pm_article_author')
        self.article = Article.objects.create(
            title='Test', slug='api-premoderation-article', content='content', author=self.article_author,
        )
        self.commenter = _create_user('api_pm_commenter')
        self.other = _create_user('api_pm_other')
        self.staff = _create_user('api_pm_staff', is_staff=True)
        self.list_url = f'/api/v1/articles/{self.article.slug}/comments/'

    def _client(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def _create_as(self, user, text='Секретный комментарий'):
        return self._client(user).post(self.list_url, {'text': text}, format='json')

    def _texts(self, resp):
        return {item['text'] for item in resp.data['results']}

    def test_premoderation_off_publishes_immediately(self):
        resp = self._create_as(self.commenter)

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data['is_approved'])
        self.assertIn('Секретный комментарий', self._texts(self._client().get(self.list_url)))

    def test_premoderation_on_creates_a_pending_comment(self):
        _set_premoderation(True)

        resp = self._create_as(self.commenter)

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertFalse(resp.data['is_approved'])
        self.assertFalse(Comment.objects.get().is_approved)

    def test_pending_comment_is_listed_only_for_its_author_and_staff(self):
        _set_premoderation(True)
        self._create_as(self.commenter)

        self.assertNotIn('Секретный комментарий', self._texts(self._client().get(self.list_url)))
        self.assertNotIn('Секретный комментарий', self._texts(self._client(self.other).get(self.list_url)))
        self.assertIn('Секретный комментарий', self._texts(self._client(self.commenter).get(self.list_url)))
        self.assertIn('Секретный комментарий', self._texts(self._client(self.staff).get(self.list_url)))

    def test_someone_elses_pending_comment_looks_like_it_does_not_exist(self):
        _set_premoderation(True)
        self._create_as(self.commenter)
        detail_url = f'{self.list_url}{Comment.objects.get().pk}/'

        self.assertEqual(self._client().get(detail_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self._client(self.other).get(detail_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self._client(self.commenter).get(detail_url).status_code, status.HTTP_200_OK)
        self.assertEqual(self._client(self.staff).get(detail_url).status_code, status.HTTP_200_OK)

    def test_staff_comment_is_published_immediately(self):
        _set_premoderation(True)

        resp = self._create_as(self.staff)

        self.assertTrue(resp.data['is_approved'])

    def test_editing_text_of_an_approved_comment_sends_it_back_to_moderation(self):
        # Иначе премодерацию обходит схема "написал безобидное, дождался одобрения, отредактировал".
        comment = Comment.objects.create(article=self.article, author=self.commenter, text='безобидный')
        _set_premoderation(True)

        resp = self._client(self.commenter).patch(f'{self.list_url}{comment.pk}/', {'text': 'другое'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertFalse(comment.is_approved)
        self.assertFalse(resp.data['is_approved'])

    def test_resending_the_same_text_keeps_the_comment_approved(self):
        comment = Comment.objects.create(article=self.article, author=self.commenter, text='безобидный')
        _set_premoderation(True)

        self._client(self.commenter).patch(f'{self.list_url}{comment.pk}/', {'text': 'безобидный'}, format='json')

        comment.refresh_from_db()
        self.assertTrue(comment.is_approved)

    def test_staff_edit_does_not_change_approval(self):
        comment = Comment.objects.create(article=self.article, author=self.commenter, text='безобидный')
        _set_premoderation(True)

        self._client(self.staff).patch(f'{self.list_url}{comment.pk}/', {'text': 'исправлено'}, format='json')

        comment.refresh_from_db()
        self.assertEqual(comment.text, 'исправлено')
        self.assertTrue(comment.is_approved)

    def test_edit_without_premoderation_keeps_the_comment_approved(self):
        comment = Comment.objects.create(article=self.article, author=self.commenter, text='безобидный')

        self._client(self.commenter).patch(f'{self.list_url}{comment.pk}/', {'text': 'другое'}, format='json')

        comment.refresh_from_db()
        self.assertTrue(comment.is_approved)

    def test_client_cannot_approve_its_own_comment(self):
        _set_premoderation(True)

        resp = self._client(self.commenter).post(
            self.list_url, {'text': 'хочу сразу', 'is_approved': True}, format='json',
        )

        self.assertFalse(resp.data['is_approved'])
        self.assertFalse(Comment.objects.get().is_approved)

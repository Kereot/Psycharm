from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedDefaultRouter

from api.views import ArticleViewSet, CommentViewSet, ConsultationViewSet, RatingViewSet, UserViewSet

router_v1 = DefaultRouter()
router_v1.register('users', UserViewSet, basename='users')
router_v1.register('articles', ArticleViewSet, basename='article')
router_v1.register('consultations', ConsultationViewSet, basename='consultation')

articles_router_v1 = NestedDefaultRouter(router_v1, 'articles', lookup='article')
articles_router_v1.register('comments', CommentViewSet, basename='article-comments')
articles_router_v1.register('ratings', RatingViewSet, basename='article-ratings')

v1_patterns = [
    path('', include(router_v1.urls)),
    path('', include(articles_router_v1.urls)),
    path('', include('djoser.urls.jwt')),
]

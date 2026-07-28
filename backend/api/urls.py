from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedDefaultRouter

from api.views import (
    ArticleViewSet,
    CommentViewSet,
    ConsultationViewSet,
    RatingViewSet,
    ServicePriceViewSet,
    UserViewSet,
)

router_v1 = DefaultRouter()
router_v1.register('users', UserViewSet, basename='users')
router_v1.register('articles', ArticleViewSet, basename='article')
router_v1.register('consultations', ConsultationViewSet, basename='consultation')
router_v1.register('prices', ServicePriceViewSet, basename='price')

articles_router_v1 = NestedDefaultRouter(router_v1, 'articles', lookup='article')
articles_router_v1.register('comments', CommentViewSet, basename='article-comments')
articles_router_v1.register('ratings', RatingViewSet, basename='article-ratings')

v1_patterns = [
    path('', include(router_v1.urls)),
    path('', include(articles_router_v1.urls)),
    path('', include('djoser.urls.jwt')),
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

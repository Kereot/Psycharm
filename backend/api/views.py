import logging
from functools import cached_property

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from djoser.views import UserViewSet as BaseUserViewSet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from api.permissions import IsAdminOrReadOnly, IsOwnerOrAdminOrReadOnly
from api.serializers import (
    ArticleSerializer,
    AvatarSerializer,
    CommentSerializer,
    ConsultationSerializer,
    ConsultationStatusUpdateSerializer,
    RatingSerializer,
    ServicePriceSerializer,
)
from articles.models import Article, Comment, Rating
from common.constants import CONSULTATION_CREATE_THROTTLE_SCOPE, CONSULTATION_STATUS_CLOSED
from common.exceptions import DuplicateRatingError
from consultations.models import Consultation
from pages.models import ServicePrice

logger = logging.getLogger(__name__)


class UserViewSet(BaseUserViewSet):
    @action(
        detail=False,
        methods=('put', 'delete'),
        url_path='me/avatar',
        serializer_class=AvatarSerializer,
        permission_classes=(IsAuthenticated,),
    )
    def avatar(self, request):
        user = request.user

        if request.method == 'PUT':
            serializer = self.get_serializer(user, data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

        if user.avatar:
            user.avatar.delete(save=False)
            user.avatar = None
            user.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


class ArticleViewSet(viewsets.ModelViewSet):
    # На реальных запросах используется get_queryset().
    queryset = Article.objects.select_related('author')
    serializer_class = ArticleSerializer
    lookup_field = 'slug'
    permission_classes = (IsAdminOrReadOnly,)

    def get_queryset(self):
        if self.request.user.is_staff:
            return self.queryset
        return self.queryset.filter(is_published=True)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


_ARTICLE_SLUG_PARAMETER = OpenApiParameter(
    name='article_slug',
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description='Slug статьи',
)
_ARTICLE_RELATION_ACTIONS = ('list', 'create', 'retrieve', 'update', 'partial_update', 'destroy')


# Убирает warning drf-spectacular на тип параметра article_slug.
@extend_schema_view(**{
    action: extend_schema(parameters=[_ARTICLE_SLUG_PARAMETER]) for action in _ARTICLE_RELATION_ACTIONS
})
class ArticleRelationViewSet(viewsets.ModelViewSet):
    permission_classes = (IsOwnerOrAdminOrReadOnly,)
    relation_model = None

    @cached_property
    def article(self):
        # Вьюсет создаётся заново на каждый запрос, так что кэш живёт ровно один запрос.
        queryset = Article.objects.all() if self.request.user.is_staff else Article.objects.filter(is_published=True)
        return get_object_or_404(queryset, slug=self.kwargs['article_slug'])

    def get_queryset(self):
        return self.relation_model.objects.filter(article=self.article).select_related('author')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['article'] = self.article
        return context

    def perform_create(self, serializer):
        serializer.save(article=self.article, author=self.request.user)


class CommentViewSet(ArticleRelationViewSet):
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer
    relation_model = Comment


class RatingViewSet(ArticleRelationViewSet):
    queryset = Rating.objects.all()
    serializer_class = RatingSerializer
    relation_model = Rating

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                super().perform_create(serializer)
        except IntegrityError:
            raise DuplicateRatingError()


class ConsultationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Consultation.objects.select_related('user')
    serializer_class = ConsultationSerializer
    throttle_scope = CONSULTATION_CREATE_THROTTLE_SCOPE

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return ConsultationStatusUpdateSerializer
        return ConsultationSerializer

    def get_throttles(self):
        # Ограничение частоты для создания заявок.
        if self.action == 'create':
            return (ScopedRateThrottle(),)
        return ()

    def get_permissions(self):
        if self.action == 'create':
            return (AllowAny(),)
        if self.action == 'my':
            return (IsAuthenticated(),)
        return (IsAdminUser(),)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        contact_method = serializer.validated_data['contact_method']
        contact_value = serializer.validated_data['contact_value']

        existing = Consultation.objects.filter(
            contact_method=contact_method, contact_value=contact_value,
        ).exclude(status=CONSULTATION_STATUS_CLOSED).first()

        if existing is not None:
            serializer.instance = existing
            return

        try:
            with transaction.atomic():
                serializer.save(user=user)
        except IntegrityError:
            serializer.instance = Consultation.objects.filter(
                contact_method=contact_method, contact_value=contact_value,
            ).exclude(status=CONSULTATION_STATUS_CLOSED).first()

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        serializer.save()

        if serializer.instance.status != old_status:
            logger.info(
                'Заявка id=%s: статус изменён %s -> %s (пользователь id=%s)',
                serializer.instance.pk, old_status, serializer.instance.status, self.request.user.pk,
            )

    @action(detail=False, methods=('get',), url_path='my')
    def my(self, request):
        queryset = Consultation.objects.filter(user=request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ServicePriceViewSet(viewsets.ModelViewSet):
    queryset = ServicePrice.objects.all()
    serializer_class = ServicePriceSerializer
    permission_classes = (IsAdminOrReadOnly,)

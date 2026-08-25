import logging
from functools import cached_property

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from djoser.views import UserViewSet as BaseUserViewSet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from api.permissions import IsAdminOrOwnerOfOpenConsultation, IsAdminOrReadOnly, IsOwnerOrAdminOrReadOnly
from api.serializers import (
    ArticleSerializer,
    AvatarSerializer,
    CommentSerializer,
    ConsultationCreateSerializer,
    ConsultationOwnerUpdateSerializer,
    ConsultationSerializer,
    ConsultationStatusUpdateSerializer,
    RatingSerializer,
    ServicePriceSerializer,
)
from articles.models import Article, Comment, Rating
from common.constants import (
    COMMENT_CREATE_THROTTLE_SCOPE,
    CONSULTATION_CREATE_UPDATE_RATE_LIMIT,
    CONSULTATION_CREATE_UPDATE_RATE_LIMIT_WINDOW_SECONDS,
)
from common.exceptions import DuplicateRatingError
from common.rate_limit import is_rate_limited
from consultations.models import Consultation
from consultations.services import claim_session_consultations, remember_anonymous_consultation
from consultations.signals import dispatch_consultation_update_notification
from pages.models import ServicePrice

logger = logging.getLogger(__name__)


class UserViewSet(BaseUserViewSet):
    def perform_create(self, serializer, *args, **kwargs):
        super().perform_create(serializer, *args, **kwargs)
        claim_session_consultations(self.request, serializer.instance)

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
    throttle_scope = COMMENT_CREATE_THROTTLE_SCOPE

    def get_throttles(self):
        # Ограничение числа потоков/исходящих соединений для уведомлений.
        if self.action == 'create':
            return (ScopedRateThrottle(),)
        return ()


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

    def get_serializer_class(self):
        if self.action == 'create':
            return ConsultationCreateSerializer
        if self.action in ('update', 'partial_update'):
            if self.request.user.is_staff:
                return ConsultationStatusUpdateSerializer
            return ConsultationOwnerUpdateSerializer
        return ConsultationSerializer

    def get_permissions(self):
        if self.action == 'create':
            return (AllowAny(),)
        if self.action == 'my':
            return (IsAuthenticated(),)
        if self.action in ('update', 'partial_update'):
            return (IsAdminOrOwnerOfOpenConsultation(),)
        return (IsAdminUser(),)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        # Лимит — только на реально валидные отправки; опечатки не тратят квоту впустую.
        sender_id = str(user.pk) if user is not None else self.request.META.get('REMOTE_ADDR', '')
        if is_rate_limited(
            'consultation_create', sender_id,
            CONSULTATION_CREATE_UPDATE_RATE_LIMIT, CONSULTATION_CREATE_UPDATE_RATE_LIMIT_WINDOW_SECONDS,
        ):
            raise Throttled(detail='Слишком много заявок. Попробуйте позже.')

        serializer.save(user=user)

        if user is None:
            remember_anonymous_consultation(self.request, serializer.instance)

    def perform_update(self, serializer):
        if not self.request.user.is_staff:
            if is_rate_limited(
                'consultation_edit', str(self.request.user.pk),
                CONSULTATION_CREATE_UPDATE_RATE_LIMIT, CONSULTATION_CREATE_UPDATE_RATE_LIMIT_WINDOW_SECONDS,
            ):
                raise Throttled(detail='Слишком много изменений. Попробуйте позже.')

        old_status = serializer.instance.status
        old_contact_method = serializer.instance.contact_method
        old_contact_value = serializer.instance.contact_value
        old_message = serializer.instance.message

        consultation = serializer.save()

        if consultation.status != old_status:
            logger.info(
                'Заявка id=%s: статус изменён %s -> %s (пользователь id=%s)',
                consultation.pk, old_status, consultation.status, self.request.user.pk,
            )

        contact_or_message_changed = (
            consultation.contact_method != old_contact_method
            or consultation.contact_value != old_contact_value
            or consultation.message != old_message
        )
        if contact_or_message_changed:
            dispatch_consultation_update_notification(consultation, old_contact_method, old_contact_value, old_message)

    @action(detail=False, methods=('get',), url_path='my')
    def my(self, request):
        queryset = Consultation.objects.filter(user=request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ServicePriceViewSet(viewsets.ModelViewSet):
    queryset = ServicePrice.objects.all()
    serializer_class = ServicePriceSerializer
    permission_classes = (IsAdminOrReadOnly,)

from functools import cached_property

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from djoser.views import UserViewSet as BaseUserViewSet
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from api.permissions import IsAdminOrReadOnly, IsOwnerOrAdminOrReadOnly
from api.serializers import (
    ArticleSerializer,
    AvatarSerializer,
    CommentSerializer,
    ConsultationSerializer,
    ConsultationStatusUpdateSerializer,
    RatingSerializer,
)
from articles.models import Article, Comment, Rating
from common.exceptions import (
    ConsultationNotificationFailed,
    DuplicateConsultationError,
    DuplicateRatingError,
    NotificationDeliveryError,
)
from consultations.models import Consultation


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
    queryset = Article.objects.select_related('author')
    serializer_class = ArticleSerializer
    lookup_field = 'slug'
    permission_classes = (IsAdminOrReadOnly,)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class ArticleRelationViewSet(viewsets.ModelViewSet):
    permission_classes = (IsOwnerOrAdminOrReadOnly,)
    relation_model = None

    @cached_property
    def article(self):
        # Вьюсет создаётся заново на каждый запрос, так что кэш живёт ровно один запрос.
        return get_object_or_404(Article, slug=self.kwargs['article_slug'])

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
        if self.action in ('update', 'partial_update'):
            return ConsultationStatusUpdateSerializer
        return ConsultationSerializer

    def get_permissions(self):
        if self.action == 'create':
            return (AllowAny(),)
        if self.action == 'my':
            return (IsAuthenticated(),)
        return (IsAdminUser(),)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        try:
            with transaction.atomic():
                serializer.save(user=user)
        except IntegrityError:
            raise DuplicateConsultationError()
        except NotificationDeliveryError:
            raise ConsultationNotificationFailed()

    @action(detail=False, methods=('get',), url_path='my')
    def my(self, request):
        queryset = Consultation.objects.filter(user=request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

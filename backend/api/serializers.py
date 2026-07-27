from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from djoser.serializers import UserSerializer as BaseUserSerializer
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from articles.models import Article, Comment, Rating
from common.constants import CONSULTATION_STATUS_CLOSED
from common.exceptions import DuplicateConsultationError, DuplicateRatingError
from common.fields import NoBlankBase64ImageField
from consultations.models import CONTACT_VALIDATORS, Consultation
from users.models import User


class UserPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'first_name', 'last_name', 'avatar')


class UserSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'avatar')
        read_only_fields = ('username', 'avatar')


class AvatarSerializer(serializers.ModelSerializer):
    avatar = NoBlankBase64ImageField(required=True)

    class Meta:
        model = User
        fields = ('avatar',)


class ArticleSerializer(serializers.ModelSerializer):
    author = UserPublicSerializer(read_only=True)

    class Meta:
        model = Article
        fields = (
            'id', 'title', 'slug', 'author', 'content', 'image',
            'is_published', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'author', 'created_at', 'updated_at')


class CommentSerializer(serializers.ModelSerializer):
    author = UserPublicSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ('id', 'author', 'text', 'created_at')
        read_only_fields = ('id', 'author', 'created_at')


class RatingSerializer(serializers.ModelSerializer):
    author = UserPublicSerializer(read_only=True)

    class Meta:
        model = Rating
        fields = ('id', 'author', 'value', 'created_at')
        read_only_fields = ('id', 'author', 'created_at')

    def validate(self, attrs):
        if self.instance is None:
            article = self.context['article']
            author = self.context['request'].user
            if Rating.objects.filter(article=article, author=author).exists():
                raise DuplicateRatingError()
        return attrs


class ConsultationSerializer(serializers.ModelSerializer):
    user = UserPublicSerializer(read_only=True)

    class Meta:
        model = Consultation
        fields = ('id', 'user', 'name', 'contact_method', 'contact_value', 'message', 'status', 'created_at',)
        read_only_fields = ('id', 'user', 'status', 'created_at')
        validators = (
            UniqueTogetherValidator(
                queryset=Consultation.objects.all(),
                fields=('contact_method', 'contact_value'),
                condition=~Q(status=CONSULTATION_STATUS_CLOSED),
                message=DuplicateConsultationError.default_detail,
            ),
        )

    def validate(self, attrs):
        if self.instance is not None:
            return attrs

        validator = CONTACT_VALIDATORS.get(attrs['contact_method'])
        if validator is not None:
            try:
                validator(attrs['contact_value'])
            except DjangoValidationError as error:
                raise serializers.ValidationError({'contact_value': error.messages})
        return attrs

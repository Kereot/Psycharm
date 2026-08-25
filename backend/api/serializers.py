from django.core.exceptions import ValidationError as DjangoValidationError
from djoser.serializers import UserSerializer as BaseUserSerializer
from rest_framework import serializers

from articles.models import Article, Comment, Rating
from common.constants import HONEYPOT_ERROR_MESSAGE, HONEYPOT_FIELD_NAME
from common.fields import NoBlankBase64ImageField
from consultations.models import Consultation
from pages.models import ServicePrice
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


def _validate_contact(contact_method, contact_value):
    instance = Consultation(contact_method=contact_method, contact_value=contact_value)
    try:
        instance.clean()
    except DjangoValidationError as error:
        raise serializers.ValidationError(error.message_dict)


class ConsultationCreateSerializer(serializers.ModelSerializer):

    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Consultation
        fields = ('name', 'contact_method', 'contact_value', 'message', 'website')

    def validate(self, attrs):
        # Honeypot: обычный пользователь это поле не видит и не заполняет, непустое значение предполагает бота.
        if attrs.pop(HONEYPOT_FIELD_NAME, ''):
            raise serializers.ValidationError({HONEYPOT_FIELD_NAME: HONEYPOT_ERROR_MESSAGE})

        _validate_contact(attrs['contact_method'], attrs['contact_value'])
        return attrs


class ConsultationOwnerUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Consultation
        fields = ('contact_method', 'contact_value', 'message')

    def validate(self, attrs):
        contact_method = attrs.get('contact_method', self.instance.contact_method)
        contact_value = attrs.get('contact_value', self.instance.contact_value)
        _validate_contact(contact_method, contact_value)
        return attrs


class ConsultationSerializer(serializers.ModelSerializer):

    user = UserPublicSerializer(read_only=True)

    class Meta:
        model = Consultation
        fields = (
            'id', 'user', 'name', 'contact_method', 'contact_value', 'message',
            'status', 'notification_failed', 'created_at',
        )
        read_only_fields = fields


class ConsultationStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consultation
        fields = ('status',)


class ServicePriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePrice
        fields = ('id', 'title', 'description', 'price', 'duration')

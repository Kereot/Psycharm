from django import forms

from articles.models import Comment, Rating
from common.constants import COMMENT_FORM_ROWS


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ('text',)
        labels = {'text': 'Комментарий'}
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control', 'rows': COMMENT_FORM_ROWS, 'placeholder': 'Ваш комментарий...',
            }),
        }


class RatingForm(forms.ModelForm):
    class Meta:
        model = Rating
        fields = ('value',)
        labels = {'value': 'Оценка'}
        widgets = {
            'value': forms.RadioSelect(),
        }

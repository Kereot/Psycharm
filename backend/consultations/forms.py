from django import forms

from common.constants import CONSULTATION_FORM_ROWS
from consultations.models import Consultation


class ConsultationForm(forms.ModelForm):
    class Meta:
        model = Consultation
        fields = ('name', 'contact_method', 'contact_value', 'message')
        labels = {
            'name': 'Ваше имя',
            'contact_method': 'Способ связи',
            'contact_value': 'Контакт',
            'message': 'Сообщение',
        }
        help_texts = {
            'contact_value': (
                'Телефон/WhatsApp: +79991234567 · Telegram: @username · Email: name@example.com'
            ),
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_method': forms.Select(attrs={'class': 'form-select'}),
            'contact_value': forms.TextInput(attrs={'class': 'form-control'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': CONSULTATION_FORM_ROWS}),
        }

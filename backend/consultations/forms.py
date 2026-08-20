from django import forms
from django.urls import reverse
from django.utils.html import format_html

from common.constants import CONSULTATION_FORM_ROWS, HONEYPOT_ERROR_MESSAGE, HONEYPOT_FIELD_NAME
from consultations.models import Consultation

# Визуально скрытое поле-приманка для ботов.
HONEYPOT_WIDGET_ATTRS = {
    'class': 'form-control',
    'autocomplete': 'off',
    'tabindex': '-1',
    'aria-hidden': 'true',
    'style': 'position:absolute; left:-9999px; width:1px; height:1px; overflow:hidden;',
}


class ConsultationForm(forms.ModelForm):
    website = forms.CharField(
        required=False,
        label='',
        widget=forms.TextInput(attrs=HONEYPOT_WIDGET_ATTRS),
    )
    privacy_consent = forms.BooleanField(
        required=True,
        label='',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['privacy_consent'].label = format_html(
            'Я согласен(на) с <a href="{}" target="_blank">политикой обработки персональных данных</a>',
            reverse('pages:privacy'),
        )

    def clean_website(self):
        value = self.cleaned_data.get(HONEYPOT_FIELD_NAME)
        if value:
            raise forms.ValidationError(HONEYPOT_ERROR_MESSAGE)
        return value

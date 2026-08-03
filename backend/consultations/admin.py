from django.contrib import admin

from consultations.models import Consultation


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_method', 'contact_value', 'status', 'notification_failed', 'created_at')
    list_filter = ('status', 'contact_method', 'notification_failed', 'created_at')
    search_fields = ('name', 'contact_value', 'message')

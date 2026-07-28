from django.contrib import admin

from pages.models import ServicePrice


@admin.register(ServicePrice)
class ServicePriceAdmin(admin.ModelAdmin):
    list_display = ('title', 'price', 'duration')
    list_editable = ('price', 'duration')

from django.apps import AppConfig


class ConsultationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'consultations'

    def ready(self):
        from consultations import signals  # noqa: F401

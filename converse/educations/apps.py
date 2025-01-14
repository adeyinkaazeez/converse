from django.apps import AppConfig


class EducationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'educations'

    def ready(self):
        import educations.signals

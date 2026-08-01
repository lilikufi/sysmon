from django.apps import AppConfig


class HostingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hosting'
    # verbose_name = ''
    # def ready(self):
    #     from .sheduler import scheduler
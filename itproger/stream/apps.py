from django.apps import AppConfig
from django.conf import settings


class StreamConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stream'

    def ready(self):
        if settings.SYSMON_ENABLE_SCHEDULER:
            from . import scheduler  # noqa: F401

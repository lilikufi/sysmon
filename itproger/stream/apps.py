from django.apps import AppConfig
from django.conf import settings


class StreamConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stream'

    def ready(self):
        if settings.SYSMON_ENABLE_SCHEDULER:
            # Disabled by default so management commands and tests stay deterministic.
            from . import sheduler  # noqa: F401

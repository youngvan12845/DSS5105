from django.apps import AppConfig


class AAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'a_agent'
    verbose_name = 'Reading Co-Pilot Agent'

    def ready(self) -> None:
        from . import signals  # noqa: F401

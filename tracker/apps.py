from django.apps import AppConfig


class TrackerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tracker'

    def ready(self):
        # Import signals so the @receiver decorators are registered with Django.
        # This must be done inside ready() to avoid circular imports at startup.
        import tracker.signals  # noqa: F401

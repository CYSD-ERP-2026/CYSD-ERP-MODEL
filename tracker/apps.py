from django.apps import AppConfig


class TrackerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tracker'

    def ready(self):
        # Import signals so the @receiver decorators are registered with Django.
        # This must be done inside ready() to avoid circular imports at startup.
        import logging
        from django.conf import settings
        import copy
        import django.template.context
        
        # Monkeypatch for Python 3.14 context copying issue
        def _patched_context_copy(self):
            duplicate = object.__new__(type(self))
            duplicate.__dict__.update(self.__dict__)
            if hasattr(self, 'dicts'):
                duplicate.dicts = [d.copy() if hasattr(d, 'copy') else d for d in self.dicts]
            return duplicate
        django.template.context.BaseContext.__copy__ = _patched_context_copy
        
        import tracker.signals  # noqa: F401

        logger = logging.getLogger(__name__)

        if not getattr(settings, 'DEBUG', False):
            # Check ALLOWED_HOSTS
            allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
            if not allowed_hosts or '*' in allowed_hosts:
                logger.warning(
                    "SECURITY WARNING: ALLOWED_HOSTS contains '*' or is empty in production (DEBUG=False)! "
                    "This makes the application vulnerable to Host Header Injection attacks."
                )

            # Check CSRF_TRUSTED_ORIGINS
            csrf_trusted_origins = getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])
            for origin in csrf_trusted_origins:
                if '*' in origin and not origin.startswith('https://*.'):
                    logger.warning(
                        f"SECURITY WARNING: CSRF_TRUSTED_ORIGINS contains wildcard origin '{origin}' in production (DEBUG=False)! "
                        "Avoid overly broad CSRF trusted origins."
                    )

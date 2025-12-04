from django.apps import AppConfig


class SystemadminConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Systemadmin'

    def ready(self):
        """Import signal handlers when app is ready"""
        import Systemadmin.signals  # noqa


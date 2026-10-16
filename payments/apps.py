from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    name = "payments"

    def ready(self):
        # Importing registers the handlers and connects the cache signals.
        from . import handlers, signals  # noqa: F401

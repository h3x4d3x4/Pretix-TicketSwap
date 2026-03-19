from django.apps import AppConfig
from django.utils.translation import gettext_lazy

from . import __version__


class TicketSwapApp(AppConfig):
    name = "pretix_ticketswap"
    verbose_name = "TicketSwap Integration"
    default_auto_field = 'django.db.models.BigAutoField'

    class PretixPluginMeta:
        name = gettext_lazy("TicketSwap Integration")
        author = "Andre Vidal"
        description = gettext_lazy(
            "Integrate your Pretix events with TicketSwap for secure ticket resale"
        )
        visible = True
        version = __version__
        category = "INTEGRATION"
        compatibility = "pretix>=2024.7.0"

    def ready(self):
        from . import signals  # noqa

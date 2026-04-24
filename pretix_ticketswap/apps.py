from django.utils.translation import gettext_lazy
from pretix.base.plugins import PluginConfig

from . import __version__


class TicketSwapApp(PluginConfig):
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

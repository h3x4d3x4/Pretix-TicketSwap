from django.utils.translation import gettext_lazy
from pretix.base.plugins import PluginConfig

from . import __version__


class TicketSwapApp(PluginConfig):
    name = "pretix_ticketswap"
    verbose_name = "TicketSwap Integration"
    default_auto_field = 'django.db.models.BigAutoField'

    class PretixPluginMeta:
        name = gettext_lazy("SecureSwap (TicketSwap) Integration")
        author = "Andre Vidal"
        description = gettext_lazy(
            "Exposes SecureSwap partner endpoints so TicketSwap can validate, "
            "swap and personalize tickets sold via your Pretix events."
        )
        visible = True
        version = __version__
        category = "INTEGRATION"
        compatibility = "pretix>=2024.7.0"

    def ready(self):
        from . import signals  # noqa

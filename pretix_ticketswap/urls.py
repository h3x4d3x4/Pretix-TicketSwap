"""URL routing for the SecureSwap plugin.

Three groups:
- Partner endpoints (``/_secureswap/api/<organizer>/...``) implementing the
  SecureSwap spec; called by TicketSwap, authenticated by Bearer token.
- Public PDF stream (``/_secureswap/pdf/<token>``) for ticket downloads via
  a signed, expiring URL.
- Admin pages (under Pretix's ``/control/`` tree) for configuration.
"""

from django.urls import re_path

from .pdf import pdf_stream_view
from .views import (
    EventGetView,
    EventsListView,
    LockView,
    PersonalizationFieldsView,
    PersonalizeView,
    SwapView,
    TicketSwapDashboardView,
    TicketSwapEventSettingsView,
    TicketSwapOrganizerSettingsView,
    TicketsListView,
    ValidateView,
)

# ---- Partner endpoints (organizer-scoped) ----

_partner_base = r"^_secureswap/api/(?P<organizer>[A-Za-z0-9._-]+)"

partner_urlpatterns = [
    # Anchor URL used by the admin dashboard's "base URL" display.
    re_path(
        _partner_base + r"/$",
        ValidateView.as_view(),  # placeholder — never matched in practice
        name="partner_root",
    ),
    re_path(
        _partner_base + r"/validate/?$",
        ValidateView.as_view(),
        name="validate",
    ),
    re_path(
        _partner_base + r"/swap/?$",
        SwapView.as_view(),
        name="swap",
    ),
    re_path(
        _partner_base + r"/personalize/?$",
        PersonalizeView.as_view(),
        name="personalize",
    ),
    re_path(
        _partner_base + r"/personalization-fields/(?P<barcode>[^/]+)/?$",
        PersonalizationFieldsView.as_view(),
        name="personalization_fields",
    ),
    re_path(
        _partner_base + r"/events/?$",
        EventsListView.as_view(),
        name="events_list",
    ),
    re_path(
        _partner_base + r"/events/(?P<id>[^/]+)/?$",
        EventGetView.as_view(),
        name="event_get",
    ),
    re_path(
        _partner_base + r"/tickets/(?P<uniqueIdentifier>[^/]+)/?$",
        TicketsListView.as_view(),
        name="tickets_list",
    ),
    re_path(
        _partner_base + r"/lock/(?P<ticketId>[^/]+)/?$",
        LockView.as_view(),
        name="lock",
    ),
]


# ---- Public PDF stream ----

pdf_urlpatterns = [
    re_path(
        r"^_secureswap/pdf/(?P<token>[^/]+)/?$",
        pdf_stream_view,
        name="pdf",
    ),
]


# ---- Pretix admin (control panel) ----

admin_urlpatterns = [
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/ticketswap/$",
        TicketSwapDashboardView.as_view(),
        name="dashboard",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/ticketswap/settings/$",
        TicketSwapEventSettingsView.as_view(),
        name="settings",
    ),
    re_path(
        r"^control/organizer/(?P<organizer>[^/]+)/secureswap/$",
        TicketSwapOrganizerSettingsView.as_view(),
        name="organizer_settings",
    ),
]


urlpatterns = partner_urlpatterns + pdf_urlpatterns + admin_urlpatterns

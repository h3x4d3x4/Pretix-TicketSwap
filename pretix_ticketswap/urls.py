"""
URL routing for TicketSwap plugin.
"""

from django.urls import re_path

from .views import (
    TicketSwapDashboardView,
    TicketSwapOrderActionView,
    TicketSwapSettingsView,
    TicketSwapTestConnectionView,
    TicketSwapWebhookView,
)

urlpatterns = [
    re_path(
        r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/ticketswap/$',
        TicketSwapDashboardView.as_view(),
        name="dashboard",
    ),
    re_path(
        r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/ticketswap/settings/$',
        TicketSwapSettingsView.as_view(),
        name="settings",
    ),
    re_path(
        r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/ticketswap/test-connection/$',
        TicketSwapTestConnectionView.as_view(),
        name="test_connection",
    ),
    re_path(
        r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/ticketswap/order-action/$',
        TicketSwapOrderActionView.as_view(),
        name="order_action",
    ),
    re_path(
        r'^_ticketswap/webhook/$',
        TicketSwapWebhookView.as_view(),
        name="webhook",
    ),
]

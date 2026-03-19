"""
Django views for TicketSwap plugin admin interface.
"""

import json
import logging

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView, TemplateView

from pretix.control.permissions import EventPermissionRequiredMixin

from .forms import TicketSwapSettingsForm
from .ticketswap_api import TicketSwapAPI, TicketSwapAPIError, TicketSwapAuthError

logger = logging.getLogger(__name__)

# Maximum webhook payload size (64KB)
MAX_WEBHOOK_PAYLOAD_SIZE = 65536


def _get_connection_status(event):
    """
    Get cached connection status for an event.

    Returns:
        Tuple of (status_string, sandbox_mode_bool)
    """
    api_key = event.settings.get("ticketswap_api_key", as_type=str, default="")
    api_secret = event.settings.get("ticketswap_api_secret", as_type=str, default="")

    if not api_key or not api_secret:
        return "not_configured", True

    cache_key = f"ticketswap_conn_{event.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached["status"], cached["sandbox"]

    try:
        api = TicketSwapAPI(api_key, api_secret)
        status = "connected" if api.test_connection() else "failed"
        sandbox = api.sandbox_mode
        cache.set(cache_key, {"status": status, "sandbox": sandbox}, 300)
        return status, sandbox
    except (TicketSwapAPIError, TicketSwapAuthError):
        cache.set(cache_key, {"status": "failed", "sandbox": True}, 60)
        return "failed", True


class TicketSwapDashboardView(EventPermissionRequiredMixin, TemplateView):
    """
    Dashboard view showing TicketSwap integration overview and statistics.
    """

    template_name = "pretix_ticketswap/dashboard.html"
    permission = "can_view_orders"

    def get_context_data(self, **kwargs):
        """Add dashboard data to context."""
        context = super().get_context_data(**kwargs)

        context["connection_status"], context["sandbox_mode"] = _get_connection_status(
            self.request.event
        )

        context["ticketswap_event_id"] = self.request.event.settings.get(
            "ticketswap_event_id", as_type=str, default=""
        )

        context["stats"] = {
            "listed_tickets": 0,
            "sold_tickets": 0,
            "secureswap_transfers": 0,
        }

        context["recent_activity"] = []

        return context


class TicketSwapTestConnectionView(EventPermissionRequiredMixin, View):
    """
    AJAX endpoint to test TicketSwap API connection.
    """

    permission = "can_change_event_settings"

    def post(self, request, *args, **kwargs):
        """Test API connection with provided credentials."""
        try:
            data = json.loads(request.body)
            api_key = data.get("api_key")
            api_secret = data.get("api_secret")

            if not api_key or not api_secret:
                return JsonResponse({
                    "success": False,
                    "message": str(_("API key and secret are required"))
                })

            api = TicketSwapAPI(api_key=api_key, api_secret=api_secret)
            if api.test_connection():
                # Invalidate cached status since credentials may have changed
                cache.delete(f"ticketswap_conn_{request.event.pk}")
                return JsonResponse({
                    "success": True,
                    "message": str(_("Connection successful! API credentials are valid."))
                })
            else:
                return JsonResponse({
                    "success": False,
                    "message": str(_("Connection failed. Please check your credentials."))
                })

        except TicketSwapAuthError:
            return JsonResponse({
                "success": False,
                "message": str(_("Invalid API credentials"))
            })
        except json.JSONDecodeError:
            return JsonResponse({
                "success": False,
                "message": str(_("Invalid request"))
            }, status=400)
        except Exception as e:
            logger.error("Connection test error: %s", e, exc_info=True)
            return JsonResponse({
                "success": False,
                "message": str(_("Connection test failed. Please verify your credentials and try again."))
            })


class TicketSwapWebhookView(View):
    """
    Webhook endpoint for receiving TicketSwap notifications.
    """

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Handle webhook from TicketSwap."""
        # Enforce payload size limit
        if len(request.body) > MAX_WEBHOOK_PAYLOAD_SIZE:
            return JsonResponse({"error": "Payload too large"}, status=413)

        # Parse JSON first so we can route to the correct event
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        event_type = data.get("event")
        ticketswap_event_id = data.get("event_id")

        if not ticketswap_event_id:
            logger.warning("Webhook missing event_id field")
            return JsonResponse({"error": "Missing event_id"}, status=400)

        # Look up the Pretix event by its stored TicketSwap event ID.
        # Hierarkey settings don't support direct queryset filtering,
        # so we iterate events that have the plugin enabled.
        from pretix.base.models import Event
        try:
            event = None
            for candidate in Event.objects.filter(plugins__contains="pretix_ticketswap"):
                stored_id = candidate.settings.get("ticketswap_event_id", as_type=str, default="")
                if stored_id == ticketswap_event_id:
                    event = candidate
                    break

            if not event:
                logger.warning("No Pretix event found for TicketSwap event %s", ticketswap_event_id)
                return JsonResponse({"error": "Unknown event"}, status=404)
        except Exception:
            logger.error("Error looking up event for webhook", exc_info=True)
            return JsonResponse({"error": "Internal server error"}, status=500)

        # Verify webhook signature
        signature = request.META.get("HTTP_X_TICKETSWAP_SIGNATURE", "")
        webhook_secret = event.settings.get("ticketswap_webhook_secret", as_type=str, default="")

        if not webhook_secret:
            logger.error("Webhook secret not configured for event %s", event.slug)
            return JsonResponse({"error": "Webhook not configured"}, status=500)

        api = TicketSwapAPI()
        if not api.verify_webhook_signature(request.body, signature, webhook_secret):
            logger.warning("Invalid webhook signature for event %s", event.slug)
            return JsonResponse({"error": "Invalid signature"}, status=401)

        logger.info("Received TicketSwap webhook: %s for event %s", event_type, event.slug)

        try:
            if event_type == "ticket.sold":
                self._handle_ticket_sold(event, data)
            elif event_type == "ticket.transferred":
                self._handle_ticket_transferred(event, data)
            elif event_type == "ticket.cancelled":
                self._handle_ticket_cancelled(event, data)
            else:
                logger.warning("Unknown webhook event type: %s", event_type)

            return JsonResponse({"status": "ok"})

        except Exception:
            logger.error("Webhook processing error", exc_info=True)
            return JsonResponse({"error": "Internal server error"}, status=500)

    def _handle_ticket_sold(self, event, data):
        """
        Handle ticket sold event.

        Marks the ticket as sold in the position meta_info.
        """
        from pretix.base.models import OrderPosition
        from .tasks import _ensure_dict

        ticket_id = data.get("ticket_id")
        logger.info("Ticket sold on TicketSwap: %s", ticket_id)

        if not ticket_id:
            return

        # Find position by stored TicketSwap ticket ID
        for position in OrderPosition.objects.filter(
            order__event=event
        ).select_related("order"):
            meta = _ensure_dict(position.meta_info)
            if meta.get("ticketswap", {}).get("ticket_id") == ticket_id:
                meta["ticketswap"]["sold"] = True
                position.meta_info = meta
                position.save(update_fields=["meta_info"])
                logger.info("Marked position %s as sold", position.id)
                break

    def _handle_ticket_transferred(self, event, data):
        """
        Handle SecureSwap transfer event.

        Invalidates the old barcode and stores the new one in Pretix
        so the new buyer can use the ticket at the door.
        """
        from pretix.base.models import OrderPosition
        from .tasks import _ensure_dict

        old_ticket_id = data.get("old_ticket_id")
        new_ticket_id = data.get("new_ticket_id")
        new_barcode = data.get("new_barcode")

        logger.info("SecureSwap: %s -> %s", old_ticket_id, new_ticket_id)

        if not old_ticket_id or not new_barcode:
            logger.error("SecureSwap webhook missing required fields (old_ticket_id or new_barcode)")
            return

        # Find the position by its stored TicketSwap ticket ID
        for position in OrderPosition.objects.filter(
            order__event=event
        ).select_related("order"):
            meta = _ensure_dict(position.meta_info)
            if meta.get("ticketswap", {}).get("ticket_id") == old_ticket_id:
                # Update the barcode (secret) so the new ticket works at the door
                position.secret = new_barcode
                meta["ticketswap"]["ticket_id"] = new_ticket_id
                meta["ticketswap"]["transferred"] = True
                meta["ticketswap"]["old_ticket_id"] = old_ticket_id
                position.meta_info = meta
                position.save(update_fields=["secret", "meta_info"])
                logger.info("Updated position %s barcode for SecureSwap", position.id)
                break

    def _handle_ticket_cancelled(self, event, data):
        """
        Handle ticket listing cancelled event.

        Updates the position meta_info to reflect the listing was cancelled.
        """
        from pretix.base.models import OrderPosition
        from .tasks import _ensure_dict

        ticket_id = data.get("ticket_id")
        logger.info("Ticket listing cancelled: %s", ticket_id)

        if not ticket_id:
            return

        for position in OrderPosition.objects.filter(
            order__event=event
        ).select_related("order"):
            meta = _ensure_dict(position.meta_info)
            if meta.get("ticketswap", {}).get("ticket_id") == ticket_id:
                meta["ticketswap"]["listed"] = False
                meta["ticketswap"]["cancelled"] = True
                position.meta_info = meta
                position.save(update_fields=["meta_info"])
                logger.info("Marked position %s listing as cancelled", position.id)
                break


class TicketSwapSettingsView(EventPermissionRequiredMixin, FormView):
    """
    View for configuring TicketSwap integration settings for an event.
    """

    template_name = "pretix_ticketswap/settings.html"
    form_class = TicketSwapSettingsForm
    permission = "can_change_event_settings"

    def get_form_kwargs(self):
        """Populate form with current settings."""
        kwargs = super().get_form_kwargs()

        kwargs["initial"] = {
            "ticketswap_enabled": self.request.event.settings.get(
                "ticketswap_enabled", as_type=bool, default=False
            ),
            "ticketswap_api_key": self.request.event.settings.get(
                "ticketswap_api_key", as_type=str, default=""
            ),
            "ticketswap_api_secret": self.request.event.settings.get(
                "ticketswap_api_secret", as_type=str, default=""
            ),
            "ticketswap_auto_enable_resale": self.request.event.settings.get(
                "ticketswap_auto_enable_resale", as_type=bool, default=True
            ),
            "ticketswap_max_resale_price_percent": self.request.event.settings.get(
                "ticketswap_max_resale_price_percent", as_type=int, default=120
            ),
            "ticketswap_webhook_secret": self.request.event.settings.get(
                "ticketswap_webhook_secret", as_type=str, default=""
            ),
        }
        return kwargs

    def form_valid(self, form):
        """Save settings when form is valid."""
        from django.contrib import messages

        for key, value in form.cleaned_data.items():
            self.request.event.settings.set(key, value)

        # Invalidate cached connection status
        cache.delete(f"ticketswap_conn_{self.request.event.pk}")

        # If enabling for the first time, try to create event on TicketSwap
        if form.cleaned_data.get("ticketswap_enabled"):
            api_key = form.cleaned_data.get("ticketswap_api_key")
            api_secret = form.cleaned_data.get("ticketswap_api_secret")

            try:
                api = TicketSwapAPI(api_key, api_secret)

                # Check if event already exists on TicketSwap (race condition guard)
                existing_id = self.request.event.settings.get(
                    "ticketswap_event_id", as_type=str, default=""
                )
                if not existing_id:
                    event_data = {
                        "name": str(self.request.event.name),
                        "date": (
                            self.request.event.date_from.isoformat()
                            if self.request.event.date_from
                            else None
                        ),
                        "location": (
                            str(self.request.event.location)
                            if self.request.event.location
                            else None
                        ),
                    }

                    result = api.create_event(event_data)
                    ticketswap_event_id = result.get("id")
                    self.request.event.settings.set(
                        "ticketswap_event_id", ticketswap_event_id
                    )

                    messages.success(
                        self.request,
                        _(
                            "TicketSwap integration enabled and event created successfully! "
                            "Event ID: {event_id}"
                        ).format(event_id=ticketswap_event_id),
                    )
                else:
                    messages.success(
                        self.request,
                        _("TicketSwap settings saved successfully!"),
                    )

            except TicketSwapAPIError as e:
                logger.error("Failed to create event on TicketSwap: %s", e)
                messages.warning(
                    self.request,
                    _(
                        "Settings saved, but failed to create event on TicketSwap. "
                        "You may need to create it manually."
                    ),
                )
        else:
            messages.success(
                self.request,
                _("TicketSwap settings saved successfully!"),
            )

        return redirect(
            reverse(
                "plugins:pretix_ticketswap:settings",
                kwargs={
                    "event": self.request.event.slug,
                    "organizer": self.request.organizer.slug,
                },
            )
        )

    def get_context_data(self, **kwargs):
        """Add additional context for template."""
        context = super().get_context_data(**kwargs)

        context["connection_status"], context["sandbox_mode"] = _get_connection_status(
            self.request.event
        )

        context["ticketswap_event_id"] = self.request.event.settings.get(
            "ticketswap_event_id", as_type=str, default=""
        )

        return context

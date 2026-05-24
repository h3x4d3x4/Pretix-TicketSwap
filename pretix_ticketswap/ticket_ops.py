"""
Domain operations for SecureSwap: position lookup, eligibility,
barcode rotation, locking, and personalization application.

All public functions take a Pretix ``Organizer`` plus partner-supplied
identifiers and either return a domain object or raise one of the
``TicketOpError`` subclasses, which the view layer renders into the
spec's ``ErrorResponse`` shape.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from django.core.cache import cache
from django.db import transaction

from .auth import enabled_events_for, is_event_enabled
from .serializers import event_uuid, position_uuid
from .utils import dump_meta, ensure_dict

logger = logging.getLogger(__name__)

META_NAMESPACE = "ticketswap"

# Cache the ticket-UUID → position.pk reverse lookup. /lock and /unlock
# always follow a prior /validate or /swap on the same ticket, so the
# cache is warm by the time we need it. TTL chosen to outlive a typical
# resale flow without keeping stale entries around indefinitely.
_TICKET_UUID_CACHE_TTL = 6 * 60 * 60  # 6h


def _uuid_cache_key(organizer_pk: int, ticket_uuid: str) -> str:
    return f"secureswap:tuuid:{organizer_pk}:{ticket_uuid}"


class TicketOpError(Exception):
    """Base; subclasses carry the spec error code."""
    error_code = "TICKET_NOT_FOUND"
    http_status = 404


class TicketNotFound(TicketOpError):
    error_code = "TICKET_NOT_FOUND"
    http_status = 404


class TicketAlreadySwapped(TicketOpError):
    error_code = "TICKET_ALREADY_SWAPPED"
    http_status = 200  # per spec, validate uses 200 even for business-rule rejects


class TicketAlreadyScanned(TicketOpError):
    error_code = "TICKET_ALREADY_SCANNED"
    http_status = 200


class OrderCancelled(TicketOpError):
    error_code = "ORDER_CANCELLED"
    http_status = 200


class ResellNotAllowed(TicketOpError):
    error_code = "RESELL_NOT_ALLOWED"
    http_status = 200


class PersonalizationNotAllowed(TicketOpError):
    error_code = "PERSONALIZATION_NOT_ALLOWED"
    http_status = 400


# ---- Lookup ----------------------------------------------------------------


def remember_uuid_for_position(organizer, position):
    """Cache ``position_uuid(position) → position.pk`` so subsequent /lock
    calls don't have to walk every position in the organizer.

    Called from /validate and /swap, which are the entry points that
    surface a ticket's UUID to TicketSwap. The cache is best-effort —
    a miss falls back to the slow scan in ``find_position_by_ticket_uuid``.
    """
    cache.set(
        _uuid_cache_key(organizer.pk, position_uuid(position)),
        position.pk,
        _TICKET_UUID_CACHE_TTL,
    )


def find_position_by_barcode(organizer, barcode: str):
    """Return the OrderPosition whose ``secret == barcode`` and whose event
    is enabled in this organizer, or ``None``.

    Side effect: remembers the position's UUID in the cache so a later
    /lock on the same ticket is O(1).
    """
    from pretix.base.models import OrderPosition

    if not barcode:
        return None

    qs = OrderPosition.objects.filter(
        order__event__organizer=organizer,
        order__event__plugins__contains="pretix_ticketswap",
        secret=barcode,
    ).select_related("order", "order__event", "item")

    for pos in qs:
        if is_event_enabled(pos.order.event):
            remember_uuid_for_position(organizer, pos)
            return pos
    return None


def find_position_by_revoked_barcode(organizer, barcode: str):
    """Return the position whose ``meta_info.ticketswap.revoked_barcodes``
    contains ``barcode``, or ``None``.

    Used by /validate to tell TicketSwap that an old, swapped-away barcode
    is *known but dead* (TICKET_ALREADY_SWAPPED) rather than unknown
    (TICKET_NOT_FOUND). The spec distinguishes these and TicketSwap's UX
    depends on the difference.
    """
    from pretix.base.models import OrderPosition

    if not barcode:
        return None

    # ``meta_info`` is a JSON-encoded TextField. A substring filter on the
    # raw barcode is a cheap pre-filter; we then verify via JSON parse.
    qs = OrderPosition.objects.filter(
        order__event__organizer=organizer,
        order__event__plugins__contains="pretix_ticketswap",
        meta_info__contains=barcode,
    ).select_related("order", "order__event", "item")

    for pos in qs.iterator(chunk_size=200):
        if not is_event_enabled(pos.order.event):
            continue
        ts = ensure_dict(pos.meta_info).get(META_NAMESPACE, {})
        if barcode in (ts.get("revoked_barcodes") or []):
            return pos
    return None


def find_position_by_ticket_uuid(organizer, ticket_uuid: str):
    """Reverse-lookup a position from its spec UUID.

    Fast path: Django cache populated by prior /validate or /swap calls.
    Slow path: scan enabled-event positions until we find the match (for
    cases where /lock arrives without a preceding /validate, e.g., a
    re-lock after a TicketSwap-side replay).
    """
    from pretix.base.models import OrderPosition

    if not ticket_uuid:
        return None

    cached_pk = cache.get(_uuid_cache_key(organizer.pk, ticket_uuid))
    if cached_pk:
        try:
            pos = (
                OrderPosition.objects
                .select_related("order", "order__event", "item")
                .get(pk=cached_pk)
            )
        except OrderPosition.DoesNotExist:
            cache.delete(_uuid_cache_key(organizer.pk, ticket_uuid))
        else:
            if (
                pos.order.event.organizer_id == organizer.pk
                and is_event_enabled(pos.order.event)
                and position_uuid(pos) == ticket_uuid
            ):
                return pos
            # Cache poisoned (position moved or UUID changed somehow) —
            # fall through to the slow scan.
            cache.delete(_uuid_cache_key(organizer.pk, ticket_uuid))

    candidate_qs = OrderPosition.objects.filter(
        order__event__organizer=organizer,
        order__event__plugins__contains="pretix_ticketswap",
    ).select_related("order", "order__event", "item").order_by("-pk")

    for pos in candidate_qs.iterator(chunk_size=500):
        if not is_event_enabled(pos.order.event):
            continue
        if position_uuid(pos) == ticket_uuid:
            remember_uuid_for_position(organizer, pos)
            return pos
    return None


def find_positions_for_unique_identifier(organizer, unique_identifier: str):
    """Spec: ``/tickets/{uniqueIdentifier}`` returns all tickets associated
    with the partner-provided identifier. We map that to the Pretix order
    code.

    Returns a list (possibly empty), restricted to enabled events.
    """
    from pretix.base.models import OrderPosition

    qs = OrderPosition.objects.filter(
        order__event__organizer=organizer,
        order__code__iexact=unique_identifier,
        canceled=False,
        addon_to__isnull=True,
    ).select_related("order", "order__event", "item")

    return [p for p in qs if is_event_enabled(p.order.event)]


# ---- Eligibility -----------------------------------------------------------


def _meta(position) -> Dict[str, Any]:
    return ensure_dict(position.meta_info).get(META_NAMESPACE, {})


def _set_meta(position, namespace_data: Dict[str, Any]):
    meta = ensure_dict(position.meta_info)
    meta[META_NAMESPACE] = namespace_data
    position.meta_info = dump_meta(meta)


def assert_swappable(position):
    """Raise the appropriate TicketOpError if the position can't be resold.

    Order matters: an already-swapped barcode is more specific than an
    order cancellation, and we want the most precise error code back.
    """
    from pretix.base.models import Order

    ts = _meta(position)

    if ts.get("swapped_to"):
        # This barcode was previously swapped away — it's an old, invalidated one.
        raise TicketAlreadySwapped()

    if ts.get("scanned") or _was_scanned(position):
        raise TicketAlreadyScanned()

    if position.canceled:
        raise OrderCancelled()
    if position.order.status in (Order.STATUS_CANCELED, Order.STATUS_EXPIRED):
        raise OrderCancelled()
    # Only paid tickets are eligible for resale — TicketSwap shouldn't be
    # able to issue a barcode for an unpaid order.
    if position.order.status != Order.STATUS_PAID:
        raise ResellNotAllowed()

    if not _is_resell_allowed(position):
        raise ResellNotAllowed()


def _was_scanned(position) -> bool:
    """Check Pretix's check-in records, not just our metadata flag.

    A ticket may have been scanned via Pretix's apps without us learning
    about it through the SecureSwap flow.
    """
    try:
        return position.checkins.exists()
    except Exception:
        # Some pretix versions or test doubles may not expose .checkins;
        # fall back to "unknown — assume not scanned".
        return False


def _is_resell_allowed(position) -> bool:
    event = position.order.event
    # Item-level deny-list for resale; default is allowed.
    if getattr(position, "item", None) is not None:
        item_id = position.item.pk
        denied_raw = event.settings.get(
            "ticketswap_excluded_item_ids", as_type=str, default=""
        ) or ""
        denied = {x.strip() for x in denied_raw.split(",") if x.strip()}
        if str(item_id) in denied:
            return False
    # Free tickets are not resellable.
    try:
        if position.price is None or float(position.price) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    return True


# ---- Mutations -------------------------------------------------------------


def _invalidate_cached_tickets(position):
    """Drop pretix's cached PDFs for this position so the next render uses
    the new secret. Best-effort: if the model isn't importable in this
    pretix version we just skip.
    """
    try:
        from pretix.base.models import CachedTicket
    except Exception:
        return
    try:
        CachedTicket.objects.filter(order_position=position).delete()
    except Exception:
        logger.exception("secureswap: failed to clear CachedTicket for pos=%s", position.pk)


def _rotate_secret(event, position) -> str:
    """Generate a new ticket secret using pretix's configured generator.

    Delegating to ``pretix.base.secrets.assign_ticket_secret`` keeps us
    aligned with pretix conventions: respects the event's chosen secret
    scheme (random / signed), writes a ``RevokedTicketSecret`` row when
    the event opts into a revocation list, and persists via Position.save.
    """
    from pretix.base.secrets import assign_ticket_secret
    assign_ticket_secret(
        event=event,
        position=position,
        force_invalidate=True,
        save=False,  # we batch the write with meta_info below
    )
    return position.secret


@transaction.atomic
def swap_barcode(position, customer: Dict[str, Any]) -> str:
    """Cancel the old barcode and assign a freshly-generated one.

    Uses pretix's ``assign_ticket_secret`` so the new value follows the
    event's configured scheme and the old one lands in
    ``RevokedTicketSecret`` when the event opts into a revocation list.
    Returns the new barcode.
    """
    from pretix.base.models import OrderPosition
    # Re-fetch under row lock so two concurrent /swap calls can't race.
    locked = (
        OrderPosition.objects
        .select_for_update()
        .select_related("order__event")
        .get(pk=position.pk)
    )

    ts = ensure_dict(locked.meta_info).get(META_NAMESPACE, {})

    # If the row lock revealed a prior swap that races against us, refuse
    # rather than orphan a freshly-issued barcode on the partner side.
    if ts.get("swapped_to") and ts.get("swapped_to") != locked.secret:
        raise TicketAlreadySwapped()

    old_barcode = locked.secret
    new_barcode = _rotate_secret(locked.order.event, locked)

    ts["last_old_barcode"] = old_barcode
    revoked = list(ts.get("revoked_barcodes") or [])
    if old_barcode and old_barcode not in revoked:
        revoked.append(old_barcode)
    # Cap to a sane length so multi-resale chains don't unbounded-grow the
    # JSON blob. 20 is comfortably above any realistic resale chain.
    ts["revoked_barcodes"] = revoked[-20:]
    ts["swap_count"] = int(ts.get("swap_count") or 0) + 1
    ts["customer"] = _trim_customer(customer)
    ts["personalized"] = False

    _set_meta(locked, ts)
    locked.save(update_fields=["secret", "meta_info"])

    _invalidate_cached_tickets(locked)

    logger.info(
        "secureswap: swapped barcode pos=%s order=%s event=%s count=%s",
        locked.pk, locked.order.code, locked.order.event.slug, ts["swap_count"],
    )
    return new_barcode


def _trim_customer(customer: Dict[str, Any]) -> Dict[str, Any]:
    """Persist only the fields we want to keep — never store password-like
    or unexpected payload fields.
    """
    keep = (
        "firstName", "lastName", "email", "language", "phone",
        "birthdate", "gender", "country", "city", "countryOfBirth",
    )
    return {k: customer.get(k) for k in keep if k in customer}


@transaction.atomic
def lock_position(position) -> None:
    """Mark a position as locked-by-TicketSwap. Spec semantics: must not
    block /validate or /swap; only blocks refunds / transfers (which we
    enforce best-effort via the meta flag — pretix's refund UI will read
    it from the dashboard warning, not from a permission hook).
    """
    from pretix.base.models import Order, OrderPosition
    locked = OrderPosition.objects.select_for_update().get(pk=position.pk)

    if locked.order.status == Order.STATUS_CANCELED:
        raise OrderCancelled()

    ts = ensure_dict(locked.meta_info).get(META_NAMESPACE, {})
    if ts.get("locked"):
        # Idempotent — spec doesn't require a 409 here.
        return

    ts["locked"] = True
    _set_meta(locked, ts)
    locked.save(update_fields=["meta_info"])

    logger.info("secureswap: locked pos=%s order=%s", locked.pk, locked.order.code)


@transaction.atomic
def unlock_position(position) -> None:
    from pretix.base.models import OrderPosition
    locked = OrderPosition.objects.select_for_update().get(pk=position.pk)
    ts = ensure_dict(locked.meta_info).get(META_NAMESPACE, {})
    if not ts.get("locked"):
        return
    ts["locked"] = False
    _set_meta(locked, ts)
    locked.save(update_fields=["meta_info"])
    logger.info("secureswap: unlocked pos=%s order=%s", locked.pk, locked.order.code)


@transaction.atomic
def apply_personalization(position, customer: Dict[str, Any]):
    """Apply customer details to a swapped position, updating cached
    attendee_name so renderers see the right name on the PDF.

    Re-personalization is allowed (spec). Rejects only if the underlying
    ticket was swapped away again (the new owner is responsible for it).
    """
    from pretix.base.models import OrderPosition
    locked = OrderPosition.objects.select_for_update().get(pk=position.pk)

    ts = ensure_dict(locked.meta_info).get(META_NAMESPACE, {})
    if not ts.get("swap_count"):
        # Personalize before swap doesn't make sense in this flow.
        raise PersonalizationNotAllowed()
    if ts.get("swapped_to") and ts.get("swapped_to") != locked.secret:
        raise PersonalizationNotAllowed()

    first = (customer.get("firstName") or "").strip()
    last = (customer.get("lastName") or "").strip()
    full = f"{first} {last}".strip()

    update_fields = ["meta_info"]
    if full:
        # attendee_name_parts is the source of truth in modern pretix.
        try:
            locked.attendee_name_parts = {"_scheme": "given_family", "given_name": first, "family_name": last, "_legacy": full}
            update_fields.append("attendee_name_parts")
        except Exception:
            pass
        try:
            locked.attendee_name_cached = full
            update_fields.append("attendee_name_cached")
        except Exception:
            pass

    email = (customer.get("email") or "").strip()
    if email:
        try:
            locked.attendee_email = email
            update_fields.append("attendee_email")
        except Exception:
            pass

    ts["personalized"] = True
    ts["customer"] = _trim_customer(customer)
    _set_meta(locked, ts)
    locked.save(update_fields=list(dict.fromkeys(update_fields)))

    _invalidate_cached_tickets(locked)

    logger.info(
        "secureswap: personalized pos=%s order=%s name=%r email=%r",
        locked.pk, locked.order.code, full or None, email or None,
    )
    return locked


def page_events(organizer, page: int, page_size: int) -> Tuple[list, int]:
    """Return (events, total_count) for the /events listing.

    Restricted to enabled events; ordered by ``date_from`` so the most
    upcoming events surface first.
    """
    enabled = [
        e for e in enabled_events_for(organizer).select_related("organizer")
        if is_event_enabled(e)
    ]
    enabled.sort(key=lambda e: e.date_from or e.id)
    total = len(enabled)
    start = max(0, (page - 1) * page_size)
    end = start + page_size
    return enabled[start:end], total


def find_event_by_uuid(organizer, event_uuid_str: str) -> Optional[Any]:
    for e in enabled_events_for(organizer).select_related("organizer"):
        if not is_event_enabled(e):
            continue
        if event_uuid(e) == event_uuid_str:
            return e
    return None

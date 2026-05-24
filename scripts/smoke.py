"""
End-to-end smoke test for the SecureSwap plugin.

Hits the real pretix request stack: URL routing, middleware, templates,
DB writes, signals, PDF rendering. Pass criterion: every assertion holds.

Usage (from the repo root):
    DATA_DIR=$(pwd)/pretix-test/data \
    DJANGO_SETTINGS_MODULE=pretix.settings \
    pretix-test/venv/bin/python3 scripts/smoke.py

The pretix-test environment must be set up (see pretix-test/QUICK_START.md);
this script seeds its own organizer / event / order / user so it can be
run repeatedly without clobbering anything else.
"""

import datetime
import json
import sys
import traceback
from decimal import Decimal

import django
django.setup()

from django.test import Client                                            # noqa: E402
from django_scopes import scope, scopes_disabled                          # noqa: E402

from pretix.base.models import (                                          # noqa: E402
    Event, Item, Order, OrderPosition, Organizer, SalesChannel, User,
)


RESULTS = []


def step(name):
    def deco(fn):
        def wrapped(*a, **kw):
            try:
                out = fn(*a, **kw)
                RESULTS.append((name, True, ""))
                return out
            except AssertionError as e:
                RESULTS.append((name, False, str(e) or "assertion failed"))
                traceback.print_exc()
            except Exception as e:
                RESULTS.append((name, False, f"{type(e).__name__}: {e}"))
                traceback.print_exc()
        return wrapped
    return deco


# ---- Seed ------------------------------------------------------------------


def seed_org(slug, name, plugin_token, team_name):
    """Idempotent: returns (organizer, user) with the user as team admin."""
    with scopes_disabled():
        org, _ = Organizer.objects.get_or_create(slug=slug, defaults={"name": name})
        user, _ = User.objects.get_or_create(
            email=f"{slug}-admin@test.local",
            defaults={"is_active": True, "is_staff": True},
        )
        user.set_password("smokepw")
        user.is_active = True
        user.is_staff = True
        user.save()

        team_qs = org.teams.filter(name=team_name)
        if team_qs.exists():
            team = team_qs.first()
        else:
            team = org.teams.create(
                name=team_name, all_events=True,
                all_event_permissions=True, all_organizer_permissions=True,
            )
        team.members.add(user)
        org.settings.set("ticketswap_partner_token", plugin_token)
        return org, user


def seed():
    with scopes_disabled():
        org, _ = Organizer.objects.get_or_create(
            slug="smoketest", defaults={"name": "Smoke Test Org"},
        )
        user, _ = User.objects.get_or_create(
            email="smoke@test.local",
            defaults={"is_active": True, "is_staff": True},
        )
        user.set_password("smokepw")
        user.is_active = True
        user.is_staff = True
        user.save()

        team_qs = org.teams.filter(name="Smokers")
        if team_qs.exists():
            team = team_qs.first()
        else:
            team = org.teams.create(
                name="Smokers",
                all_events=True,
                all_event_permissions=True,
                all_organizer_permissions=True,
            )
        team.members.add(user)

        event, _ = Event.objects.get_or_create(
            organizer=org, slug="smokeevt",
            defaults={
                "name": "Smoke Event",
                "currency": "EUR",
                "date_from": datetime.datetime(
                    2026, 12, 31, 18, 0, tzinfo=datetime.timezone.utc,
                ),
                "is_public": True,
                "live": True,
                "plugins": "pretix_ticketswap,pretix.plugins.ticketoutputpdf",
            },
        )
        # Persist plugin list — get_or_create wouldn't update an existing row
        event.plugins = "pretix_ticketswap,pretix.plugins.ticketoutputpdf"
        event.save(update_fields=["plugins"])
        event.settings.set("ticketswap_enabled", True)
        event.settings.set("ticketswap_personalization_required", False)
        event.settings.set("ticketswap_venue_country", "NL")
        event.settings.set("ticketswap_venue_city", "Amsterdam")
        event.settings.set("ticketswap_event_type", "FESTIVAL")

        # Organizer-level partner token
        org.settings.set("ticketswap_partner_token", "smoke-token-abc")

        return org, event, user


def seed_event(org, slug, name, plugin_enabled=True, personalization_required=False):
    with scopes_disabled():
        event, _ = Event.objects.get_or_create(
            organizer=org, slug=slug,
            defaults={
                "name": name, "currency": "EUR",
                "date_from": datetime.datetime(
                    2026, 12, 31, 18, 0, tzinfo=datetime.timezone.utc,
                ),
                "is_public": True, "live": True,
                "plugins": "pretix_ticketswap,pretix.plugins.ticketoutputpdf",
            },
        )
        event.plugins = "pretix_ticketswap,pretix.plugins.ticketoutputpdf"
        event.save(update_fields=["plugins"])
        event.settings.set("ticketswap_enabled", plugin_enabled)
        event.settings.set(
            "ticketswap_personalization_required", personalization_required,
        )
        event.settings.set("ticketswap_event_type", "FESTIVAL")
        event.settings.set("ticketswap_venue_country", "NL")
        return event


def seed_paid_order(org, event, code="SM001", price="25.00",
                    status=Order.STATUS_PAID, with_position=True):
    with scope(organizer=org):
        item, _ = Item.objects.get_or_create(
            event=event, name="GA",
            defaults={"default_price": Decimal(price), "admission": True},
        )
        # Always start with a fresh order so swap tests don't see leftover state
        for o in Order.objects.filter(event=event, code=code):
            o.positions.all().delete()
            o.delete()
        # Pretix requires every order to belong to a SalesChannel. Reuse the
        # organizer's "web" channel (auto-created on first event) or fall back
        # to creating one.
        channel = (
            SalesChannel.objects.filter(organizer=org, identifier="web").first()
            or SalesChannel.objects.filter(organizer=org).first()
        )
        if channel is None:
            channel = SalesChannel.objects.create(
                organizer=org, identifier="web",
                label="Web shop", type="web",
            )
        order = Order.objects.create(
            event=event, code=code, status=status,
            email="buyer@example.com", expires=datetime.datetime(
                2026, 12, 31, tzinfo=datetime.timezone.utc,
            ),
            total=Decimal(price), locale="en",
            datetime=datetime.datetime.now(datetime.timezone.utc),
            sales_channel=channel,
        )
        if not with_position:
            return order, None, item
        position = OrderPosition.objects.create(
            order=order, item=item, price=Decimal(price),
            attendee_name_parts={"_scheme": "given_family",
                                 "given_name": "Alice", "family_name": "Doe"},
        )
        return order, position, item


# ---- Tests -----------------------------------------------------------------


def auth_header():
    return {"HTTP_AUTHORIZATION": "Bearer smoke-token-abc"}


@step("admin: organizer settings page renders")
def test_organizer_settings_renders(client, org):
    r = client.get(f"/control/organizer/{org.slug}/secureswap/")
    assert r.status_code == 200, f"got {r.status_code}: {r.content[:200]!r}"
    body = r.content.decode()
    assert "SecureSwap" in body
    assert "Partner token" in body
    assert f"/_secureswap/api/{org.slug}/" in body


@step("admin: event dashboard renders + shows base URL")
def test_event_dashboard_renders(client, org, event):
    r = client.get(f"/control/event/{org.slug}/{event.slug}/ticketswap/")
    assert r.status_code == 200, f"got {r.status_code}: {r.content[:300]!r}"
    body = r.content.decode()
    assert "SecureSwap" in body
    assert f"/_secureswap/api/{org.slug}/" in body
    assert "validate?barcode" in body


@step("admin: event settings form renders")
def test_event_settings_renders(client, org, event):
    r = client.get(f"/control/event/{org.slug}/{event.slug}/ticketswap/settings/")
    assert r.status_code == 200, f"got {r.status_code}: {r.content[:300]!r}"
    assert "Personalization fields" in r.content.decode()


@step("partner: validate happy path returns ValidationResponse")
def test_validate_happy(client, org, position):
    r = client.get(
        f"/_secureswap/api/{org.slug}/validate?barcode={position.secret}",
        **auth_header(),
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.content[:300]!r}"
    body = json.loads(r.content)
    assert body["valid"] is True, body
    assert body["swappable"] is True, body
    assert body["barcode"] == position.secret
    assert body["event"]["name"] == "Smoke Event"
    assert body["pdf"], "expected pdf URL, got falsy"
    assert r["Cache-Control"] == "no-store"


@step("partner: validate without auth returns 401 UNAUTHORIZED")
def test_validate_unauth(client, org, position):
    r = client.get(f"/_secureswap/api/{org.slug}/validate?barcode={position.secret}")
    assert r.status_code == 401, f"got {r.status_code}"
    body = json.loads(r.content)
    assert body["error"] == "UNAUTHORIZED"


@step("partner: validate unknown barcode returns 404 TICKET_NOT_FOUND")
def test_validate_unknown(client, org):
    r = client.get(
        f"/_secureswap/api/{org.slug}/validate?barcode=DOESNOTEXIST",
        **auth_header(),
    )
    assert r.status_code == 404, f"got {r.status_code}"
    body = json.loads(r.content)
    assert body["error"] == "TICKET_NOT_FOUND"


@step("partner: events list paginated")
def test_events_list(client, org, event):
    r = client.get(f"/_secureswap/api/{org.slug}/events?page=1&page_size=10", **auth_header())
    assert r.status_code == 200, f"got {r.status_code}: {r.content[:300]!r}"
    body = json.loads(r.content)
    assert len(body["events"]) >= 1
    assert body["pagination"]["page"] == 1
    # The Smoke Event has venue_city=Amsterdam — locate it specifically since
    # other events from earlier runs may be in the listing too.
    smoke = next((e for e in body["events"] if e["name"] == "Smoke Event"), None)
    assert smoke is not None, f"Smoke Event not found in: {[e['name'] for e in body['events']]}"
    assert smoke["type"] == "FESTIVAL", smoke
    assert smoke["venue"]["country"] == "NL"
    assert smoke["venue"]["city"] == "Amsterdam"
    assert smoke["ticket_types"], "expected at least one ticket type"


@step("partner: tickets list by order code")
def test_tickets_list(client, org, order):
    r = client.get(f"/_secureswap/api/{org.slug}/tickets/{order.code}", **auth_header())
    assert r.status_code == 200, f"got {r.status_code}: {r.content[:300]!r}"
    body = json.loads(r.content)
    assert len(body["tickets"]) == 1
    assert body["tickets"][0]["barcode"]


@step("partner: personalization-fields returns defaults for unconfigured event")
def test_personalization_fields(client, org, position):
    r = client.get(
        f"/_secureswap/api/{org.slug}/personalization-fields/{position.secret}",
        **auth_header(),
    )
    assert r.status_code == 200, f"got {r.status_code}"
    body = json.loads(r.content)
    assert any(f["name"] == "first_name" for f in body)


@step("partner: swap rotates the barcode and returns a PDF URL")
def test_swap(client, org, position):
    old_barcode = position.secret
    r = client.post(
        f"/_secureswap/api/{org.slug}/swap",
        data=json.dumps({
            "ticket": {"barcode": old_barcode},
            "customer": {"firstName": "Bob", "lastName": "X",
                         "email": "b@x.com", "language": "en"},
        }),
        content_type="application/json",
        **auth_header(),
    )
    assert r.status_code == 201, f"got {r.status_code}: {r.content[:400]!r}"
    body = json.loads(r.content)
    assert body["barcode"] != old_barcode, "barcode did not rotate"
    assert body["pdf"], "expected pdf URL on /swap response"
    # Persistence check: the position's secret in the DB should reflect the new value
    position.refresh_from_db()
    assert position.secret == body["barcode"]
    return body["barcode"], body["pdf"]


@step("partner: lock + unlock the rotated ticket")
def test_lock_unlock(client, org, position):
    # First obtain the ticket UUID by hitting /validate again — populates cache
    r = client.get(
        f"/_secureswap/api/{org.slug}/validate?barcode={position.secret}",
        **auth_header(),
    )
    assert r.status_code == 200
    ticket_id = json.loads(r.content)["id"]

    r = client.post(f"/_secureswap/api/{org.slug}/lock/{ticket_id}", **auth_header())
    assert r.status_code == 201, f"lock got {r.status_code}: {r.content[:300]!r}"

    r = client.delete(f"/_secureswap/api/{org.slug}/lock/{ticket_id}", **auth_header())
    assert r.status_code == 204, f"unlock got {r.status_code}"


@step("public: PDF stream serves the regenerated ticket")
def test_pdf_stream(client, pdf_url):
    # pdf_url is absolute; strip scheme/host so the test client treats it as a path
    from urllib.parse import urlparse
    path = urlparse(pdf_url).path
    r = client.get(path)
    assert r.status_code == 200, f"got {r.status_code}: {r.content[:300]!r}"
    # PDFs always start with %PDF-
    assert r.content[:5] == b"%PDF-", f"not a PDF; first bytes: {r.content[:20]!r}"


# ---- Additional coverage --------------------------------------------------


@step("partner: /events/{id} returns single event")
def test_event_get(client, org, event):
    from pretix_ticketswap.serializers import event_uuid
    uuid = event_uuid(event)
    r = client.get(f"/_secureswap/api/{org.slug}/events/{uuid}", **auth_header())
    assert r.status_code == 200, f"got {r.status_code}: {r.content[:300]!r}"
    body = json.loads(r.content)
    assert body["id"] == uuid
    assert body["name"] == "Smoke Event"
    # Unknown UUID → 404
    r = client.get(f"/_secureswap/api/{org.slug}/events/aaaa-bbbb", **auth_header())
    assert r.status_code == 404


@step("partner: /swap on free ticket returns RESELL_NOT_ALLOWED")
def test_swap_rejects_free_ticket(client, org, event):
    _order, free_pos, _item = seed_paid_order(
        org, event, code="SMFREE", price="0.00",
    )
    r = client.post(
        f"/_secureswap/api/{org.slug}/swap",
        data=json.dumps({
            "ticket": {"barcode": free_pos.secret},
            "customer": {"firstName": "X", "lastName": "Y",
                         "email": "x@y.com", "language": "en"},
        }),
        content_type="application/json",
        **auth_header(),
    )
    assert r.status_code == 400, f"got {r.status_code}: {r.content[:300]!r}"
    body = json.loads(r.content)
    assert body["error"] == "RESELL_NOT_ALLOWED", body


@step("partner: /swap on canceled order returns RESELL_NOT_ALLOWED")
def test_swap_rejects_canceled_order(client, org, event):
    _order, canc_pos, _item = seed_paid_order(
        org, event, code="SMCANC", status=Order.STATUS_CANCELED,
    )
    r = client.post(
        f"/_secureswap/api/{org.slug}/swap",
        data=json.dumps({
            "ticket": {"barcode": canc_pos.secret},
            "customer": {"firstName": "X", "lastName": "Y",
                         "email": "x@y.com", "language": "en"},
        }),
        content_type="application/json",
        **auth_header(),
    )
    assert r.status_code == 400, f"got {r.status_code}: {r.content[:300]!r}"
    body = json.loads(r.content)
    assert body["error"] == "RESELL_NOT_ALLOWED", body


@step("partner: multi-resale (sequential /swap rotates again; old barcode reports ALREADY_SWAPPED)")
def test_multi_resale(client, org, event):
    # Fresh ticket so prior test_swap state doesn't bleed in.
    _order, pos, _item = seed_paid_order(org, event, code="SMMULTI", price="30.00")
    first_barcode = pos.secret

    def swap(current_barcode):
        return client.post(
            f"/_secureswap/api/{org.slug}/swap",
            data=json.dumps({
                "ticket": {"barcode": current_barcode},
                "customer": {"firstName": "A", "lastName": "B",
                             "email": "a@b.com", "language": "en"},
            }),
            content_type="application/json",
            **auth_header(),
        )

    r1 = swap(first_barcode)
    assert r1.status_code == 201, f"first swap failed: {r1.status_code}"
    second_barcode = json.loads(r1.content)["barcode"]
    assert second_barcode != first_barcode

    r2 = swap(second_barcode)
    assert r2.status_code == 201, f"second swap failed: {r2.status_code} {r2.content[:300]!r}"
    third_barcode = json.loads(r2.content)["barcode"]
    assert third_barcode != second_barcode and third_barcode != first_barcode

    # /validate on the long-dead first barcode must report TICKET_ALREADY_SWAPPED
    # (not TICKET_NOT_FOUND) so TicketSwap knows the ticket exists but is dead.
    r = client.get(
        f"/_secureswap/api/{org.slug}/validate?barcode={first_barcode}",
        **auth_header(),
    )
    body = json.loads(r.content)
    assert body["error"] == "TICKET_ALREADY_SWAPPED", \
        f"expected TICKET_ALREADY_SWAPPED for revoked barcode, got {body}"


@step("partner: personalization flow (require → swap returns pdf:null → personalize applies name)")
def test_personalization_flow(client, org):
    # New event configured with personalization required.
    p_event = seed_event(
        org, slug="smokepers", name="Personalization Event",
        plugin_enabled=True, personalization_required=True,
    )
    _order, p_pos, _item = seed_paid_order(org, p_event, code="SMPERS")

    # /swap should now return pdf:null + personalization_required:true
    r = client.post(
        f"/_secureswap/api/{org.slug}/swap",
        data=json.dumps({
            "ticket": {"barcode": p_pos.secret},
            "customer": {"firstName": "A", "lastName": "B",
                         "email": "a@b.com", "language": "en"},
        }),
        content_type="application/json",
        **auth_header(),
    )
    assert r.status_code == 201, f"swap got {r.status_code}: {r.content[:300]!r}"
    body = json.loads(r.content)
    assert body["pdf"] is None, f"expected null pdf, got {body['pdf']!r}"
    assert body.get("personalization_required") is True
    p_pos.refresh_from_db()
    new_barcode = p_pos.secret

    # /personalize should apply name + return PDF URL
    r = client.post(
        f"/_secureswap/api/{org.slug}/personalize",
        data=json.dumps({
            "ticket": {"barcode": new_barcode},
            "customer": {"firstName": "Charlie", "lastName": "Personal",
                         "email": "c@p.com", "language": "en"},
        }),
        content_type="application/json",
        **auth_header(),
    )
    assert r.status_code == 200, f"personalize got {r.status_code}: {r.content[:400]!r}"
    body = json.loads(r.content)
    assert body["pdf"], "expected pdf URL on /personalize response"

    p_pos.refresh_from_db()
    parts = p_pos.attendee_name_parts or {}
    assert parts.get("given_name") == "Charlie", parts
    assert parts.get("family_name") == "Personal", parts

    # Re-personalize with different name — must overwrite
    r = client.post(
        f"/_secureswap/api/{org.slug}/personalize",
        data=json.dumps({
            "ticket": {"barcode": new_barcode},
            "customer": {"firstName": "Delta", "lastName": "Two",
                         "email": "d@p.com", "language": "en"},
        }),
        content_type="application/json",
        **auth_header(),
    )
    assert r.status_code == 200
    p_pos.refresh_from_db()
    assert (p_pos.attendee_name_parts or {}).get("given_name") == "Delta"


@step("partner: cross-organizer isolation (token A can't act on org B tickets)")
def test_cross_organizer_isolation(client_b, org_a, position_a):
    """``client_b`` carries org B's token; org A's barcode must look unknown to it."""
    r = client_b.get(
        f"/_secureswap/api/{org_a.slug}/validate?barcode={position_a.secret}",
        HTTP_AUTHORIZATION="Bearer wrong-org-token",
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.content[:200]!r}"

    # Also: org B's correct token used against org A's URL → 401
    r = client_b.get(
        f"/_secureswap/api/{org_a.slug}/validate?barcode={position_a.secret}",
        HTTP_AUTHORIZATION="Bearer org-b-token",
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.content[:200]!r}"


# ---- Run -------------------------------------------------------------------


def main():
    print("=== Seeding ===")
    org, event, user = seed()
    print(f"  org={org.slug}  event={event.slug}  user={user.email}")
    order, position, item = seed_paid_order(org, event)
    print(f"  order={order.code}  position pk={position.pk}  secret={position.secret}")

    # Second organizer for cross-isolation tests.
    org_b, _ = seed_org(
        slug="smoketestb", name="Smoke Test Org B",
        plugin_token="org-b-token", team_name="SmokersB",
    )
    print(f"  org_b={org_b.slug}  (isolation tests)")

    client = Client()
    assert client.login(email=user.email, password="smokepw"), "login failed"
    client_b = Client()  # unauthenticated, used only for partner-endpoint calls

    with scope(organizer=org):
        test_organizer_settings_renders(client, org)
        test_event_dashboard_renders(client, org, event)
        test_event_settings_renders(client, org, event)
        test_validate_happy(client, org, position)
        test_validate_unauth(client, org, position)
        test_validate_unknown(client, org)
        test_events_list(client, org, event)
        test_event_get(client, org, event)
        test_tickets_list(client, org, order)
        test_personalization_fields(client, org, position)
        swap_result = test_swap(client, org, position)
        test_lock_unlock(client, org, position)
        if swap_result:
            _new_barcode, pdf_url = swap_result
            test_pdf_stream(client, pdf_url)
        test_swap_rejects_free_ticket(client, org, event)
        test_swap_rejects_canceled_order(client, org, event)
        test_multi_resale(client, org, event)
        test_personalization_flow(client, org)

    # Cross-isolation test uses a separate scope so org_b lookups don't
    # accidentally inherit org A's scope.
    with scope(organizer=org_b):
        test_cross_organizer_isolation(client_b, org, position)

    print()
    print("=== Results ===")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    for name, ok, err in RESULTS:
        marker = "PASS" if ok else "FAIL"
        line = f"  [{marker}] {name}"
        if err:
            line += f"  --  {err}"
        print(line)
    print(f"\n  {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

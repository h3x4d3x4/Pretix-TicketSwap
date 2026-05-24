"""
One-shot cleanup of v1 settings that are no longer read in v2.0+.

The 1.x plugin stored ``ticketswap_api_key`` / ``ticketswap_api_secret`` /
``ticketswap_webhook_secret`` / ``ticketswap_event_id`` / ``ticketswap_auto_enable_resale``
/ ``ticketswap_max_resale_price_percent`` per-event. None of those are read
in v2.0+, but they'd otherwise sit forever in Hierarkey's settings table.

This migration runs once per ``pretix migrate`` invocation. It's idempotent:
re-running it on a database where the keys are already gone is a no-op.

Schema-only migration with zero operations on our own models — pretix
plugins don't have to define any.
"""

from django.db import migrations


V1_ORPHAN_KEYS = (
    "ticketswap_api_key",
    "ticketswap_api_secret",
    "ticketswap_webhook_secret",
    "ticketswap_event_id",
    "ticketswap_auto_enable_resale",
    "ticketswap_max_resale_price_percent",
)


def cleanup_v1_settings(apps, schema_editor):
    # Hierarkey settings are runtime-only; the migration framework's
    # historical models don't expose the ``.settings`` accessor. Use the
    # live Event model — safe because settings live in their own table.
    # ``django_scopes`` requires an explicit scope window for any Event
    # query, so we wrap the whole pass in ``scopes_disabled``.
    from django_scopes import scopes_disabled
    from pretix.base.models import Event

    affected = 0
    with scopes_disabled():
        for event in Event.objects.filter(plugins__contains="pretix_ticketswap"):
            for key in V1_ORPHAN_KEYS:
                if event.settings.get(key, as_type=str, default=None) is not None:
                    event.settings.delete(key)
                    affected += 1
    if affected:
        print(f"  cleaned up {affected} orphaned v1 SecureSwap settings")


def reverse_noop(apps, schema_editor):
    # The values are gone for a reason — there's nothing to restore.
    pass


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.RunPython(cleanup_v1_settings, reverse_code=reverse_noop),
    ]

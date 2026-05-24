"""
Top-level pytest configuration.

The plugin imports a few symbols from ``pretix.base.models`` and
``pretix.control.permissions``, which require Django to be configured
before they can be imported. We point Django at the pretix-provided
test settings module up-front so even pure-unit tests can ``import
pretix_ticketswap.<anything>`` without exploding.
"""

import os

import django


def pytest_configure(config):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.testutils.settings")
    django.setup()

"""Integration contract: the real DB-URL fixtures never yield ``localhost``.

Complements the unit contract (tests/unit/test_testcontainers_ipv4_contract.py)
by exercising the ACTUAL session fixtures against a real database
(Testcontainers or an external DB). On Windows a ``localhost`` host means the
slow IPv6-first path silently came back; assert IPv4 loopback (or a non-loopback
external host) instead.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.integration


def test_async_url_has_no_windows_localhost(test_database_url: str) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows-only IPv6-loopback contract")
    assert (
        "@localhost:" not in test_database_url and "@localhost/" not in test_database_url
    ), f"Windows test DB URL still uses localhost (slow IPv6-first path): {test_database_url}"


def test_sync_url_has_no_windows_localhost(test_database_url_sync: str) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows-only IPv6-loopback contract")
    assert (
        "@localhost:" not in test_database_url_sync and "@localhost/" not in test_database_url_sync
    ), f"Windows sync test DB URL still uses localhost: {test_database_url_sync}"

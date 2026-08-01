"""Opening a provider client — the three ways it is unusable, and the close.

This module decides whether a provider can be reached at all, and it owns the
transport cleanup. Both were exercised only indirectly (the fetchers patch it),
which left two real classes of defect unpinned:

- an unusable connector must raise ``ProviderNotConfigured`` for EVERY reason
  it can be unusable — a missed branch would return a half-built client and
  fail deep inside a fetcher, where the caller can no longer tell "not plugged
  in" from "the read failed";
- the per-instance httpx transport must be closed on EVERY path, including the
  one where the body raised. A transport left open is a resource warning at
  teardown and a leak under load.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.relations.providers.client import ProviderNotConfigured, open_category_client

pytestmark = pytest.mark.unit

USER_ID = uuid4()


def _patched(
    *,
    resolved_type: object | None = SimpleNamespace(is_apple=False),
    credentials: object | None = {"token": "x"},
    client_class: object | None = None,
    client: object | None = None,
):
    """Patch the whole resolution chain; each knob turns one branch off."""
    built = client if client is not None else SimpleNamespace(close=AsyncMock())
    factory = MagicMock(return_value=built) if client_class is None else client_class

    @contextlib.asynccontextmanager
    async def _db():
        yield SimpleNamespace()

    service = MagicMock()
    service.get_connector_credentials = AsyncMock(return_value=credentials)
    service.get_apple_credentials = AsyncMock(return_value=credentials)

    return (
        patch("src.domains.relations.providers.client.get_db_context", _db),
        patch("src.domains.relations.providers.client.ConnectorService", return_value=service),
        patch(
            "src.domains.relations.providers.client.resolve_active_connector",
            new=AsyncMock(return_value=resolved_type),
        ),
        patch(
            "src.domains.relations.providers.client.ClientRegistry.get_client_class",
            return_value=factory,
        ),
        built,
    )


class TestUnusableProvider:
    """Three reasons, one sentence for the reader: it is not plugged in."""

    async def test_no_active_connector(self) -> None:
        p_db, p_svc, p_resolve, p_reg, _ = _patched(resolved_type=None)
        with p_db, p_svc, p_resolve, p_reg, pytest.raises(ProviderNotConfigured):
            async with open_category_client("contacts", USER_ID):
                pass

    async def test_credentials_are_gone(self) -> None:
        p_db, p_svc, p_resolve, p_reg, _ = _patched(credentials=None)
        with p_db, p_svc, p_resolve, p_reg, pytest.raises(ProviderNotConfigured):
            async with open_category_client("email", USER_ID):
                pass

    async def test_no_client_registered_for_that_connector(self) -> None:
        p_db, p_svc, p_resolve, p_reg, _ = _patched(client_class=None)
        with (
            p_db,
            p_svc,
            p_resolve,
            patch(
                "src.domains.relations.providers.client.ClientRegistry.get_client_class",
                return_value=None,
            ),
            pytest.raises(ProviderNotConfigured),
        ):
            async with open_category_client("calendar", USER_ID):
                pass


class TestWhatTravelsWithTheClient:
    async def test_carries_the_connector_type_and_the_session(self) -> None:
        """Reading an OWNER's default calendar needs both — and reading the
        wrong container is the costliest wrong answer this codebase recorded."""
        resolved = SimpleNamespace(is_apple=False)
        p_db, p_svc, p_resolve, p_reg, built = _patched(resolved_type=resolved)
        with p_db, p_svc, p_resolve, p_reg:
            async with open_category_client("calendar", USER_ID) as opened:
                assert opened.client is built
                assert opened.connector_type is resolved
                assert opened.session is not None

    async def test_an_apple_connector_reads_its_own_credentials(self) -> None:
        p_db, p_svc, p_resolve, p_reg, _ = _patched(resolved_type=SimpleNamespace(is_apple=True))
        with p_db, p_svc as service_ctor, p_resolve, p_reg:
            async with open_category_client("calendar", USER_ID):
                pass
        service = service_ctor.return_value
        service.get_apple_credentials.assert_awaited_once()
        service.get_connector_credentials.assert_not_awaited()


class TestTransportIsAlwaysClosed:
    async def test_closed_on_the_happy_path(self) -> None:
        p_db, p_svc, p_resolve, p_reg, built = _patched()
        with p_db, p_svc, p_resolve, p_reg:
            async with open_category_client("email", USER_ID):
                pass
        built.close.assert_awaited_once()

    async def test_closed_even_when_the_body_raises(self) -> None:
        """The leak that only shows under load, never in a happy-path test."""
        p_db, p_svc, p_resolve, p_reg, built = _patched()
        with p_db, p_svc, p_resolve, p_reg, pytest.raises(TimeoutError):
            async with open_category_client("email", USER_ID):
                raise TimeoutError("provider hung")
        built.close.assert_awaited_once()

    async def test_a_client_without_close_is_not_a_crash(self) -> None:
        """Not every registered client owns a transport."""
        p_db, p_svc, p_resolve, p_reg, _ = _patched(client=SimpleNamespace())
        with p_db, p_svc, p_resolve, p_reg:
            async with open_category_client("contacts", USER_ID) as opened:
                assert opened.client is not None

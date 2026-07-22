"""Person-360 overview tool (P3, ADR-141).

One call aggregates contact card + recent emails + upcoming events +
relevant memories, each sub-fetch independently failable — the overview is
honestly partial (``partial_failures``) rather than all-or-nothing.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _config():
    return SimpleNamespace(user_id=str(uuid4()))


async def _call(monkey_fetchers: dict, person="Marie"):
    from src.domains.agents.tools import person_tools

    patches = [
        patch.object(person_tools, "validate_runtime_config", return_value=_config()),
    ]
    for name, mock in monkey_fetchers.items():
        patches.append(patch.object(person_tools, name, mock))
    ctx = patches[0]
    with ctx:
        inner = patches[1:]
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in inner:
                stack.enter_context(p)
            return await person_tools.get_person_overview_tool.coroutine(
                person_name=person, runtime=MagicMock()
            )


def _all_fetchers_ok():
    return {
        "_fetch_contact_card": AsyncMock(
            return_value={"name": "Marie Dupont", "emails": ["marie@x.fr"], "phones": []}
        ),
        "_fetch_recent_emails": AsyncMock(
            return_value=[{"subject": "Devis", "from": "marie@x.fr", "date": "2026-07-20"}]
        ),
        "_fetch_upcoming_events": AsyncMock(
            return_value=[{"title": "Café avec Marie", "start": "2026-07-24 15:00"}]
        ),
        "_fetch_person_memories": AsyncMock(return_value=["Marie préfère être appelée le matin"]),
    }


@pytest.mark.unit
class TestGetPersonOverview:
    async def test_full_overview_aggregates_all_blocks(self):
        output = await _call(_all_fetchers_ok())

        assert output.success is True
        data = output.structured_data
        assert data["contact"]["name"] == "Marie Dupont"
        assert data["recent_emails"][0]["subject"] == "Devis"
        assert data["upcoming_events"][0]["title"] == "Café avec Marie"
        assert data["memories"] == ["Marie préfère être appelée le matin"]
        assert data["partial_failures"] == []

    async def test_single_subfetch_failure_yields_partial_overview(self):
        fetchers = _all_fetchers_ok()
        fetchers["_fetch_recent_emails"] = AsyncMock(side_effect=RuntimeError("gmail down"))
        output = await _call(fetchers)

        assert output.success is True
        data = output.structured_data
        assert data["recent_emails"] == []
        assert "emails" in data["partial_failures"]
        # The rest survives
        assert data["contact"]["name"] == "Marie Dupont"
        assert data["memories"]

    async def test_unknown_person_returns_not_found(self):
        fetchers = _all_fetchers_ok()
        fetchers["_fetch_contact_card"] = AsyncMock(return_value=None)
        output = await _call(fetchers, person="Inconnu Total")

        assert output.success is False
        assert output.error_code == "person_not_found"

    async def test_missing_connector_is_skipped_not_failed(self):
        """A sub-fetch returning None (no connector) is neither data nor failure."""
        fetchers = _all_fetchers_ok()
        fetchers["_fetch_upcoming_events"] = AsyncMock(return_value=None)
        output = await _call(fetchers)

        assert output.success is True
        data = output.structured_data
        assert data["upcoming_events"] == []
        assert "events" not in data["partial_failures"]


def _provider_client(**methods):
    """Resolved provider client double — every transport owns a close()."""
    client = MagicMock()
    client.close = AsyncMock()
    for name, mock in methods.items():
        setattr(client, name, mock)
    return client


@pytest.mark.unit
class TestProviderClientLifecycle:
    """Each resolved provider client carries its own HTTP transport: the
    fetcher that resolves it OWNS it and must close it on every path
    (systemic rule — unclosed transports are failures)."""

    async def test_contact_card_closes_client_on_success(self):
        from src.domains.agents.tools import person_tools

        client = _provider_client(
            search_contacts=AsyncMock(return_value={"results": [{"person": {"names": []}}]})
        )
        with patch.object(person_tools, "_resolve_provider_client", AsyncMock(return_value=client)):
            await person_tools._fetch_contact_card(uuid4(), "Marie")
        client.close.assert_awaited_once()

    async def test_recent_emails_closes_client_on_provider_error(self):
        from src.domains.agents.tools import person_tools

        client = _provider_client(search_emails=AsyncMock(side_effect=RuntimeError("gmail down")))
        with patch.object(person_tools, "_resolve_provider_client", AsyncMock(return_value=client)):
            with pytest.raises(RuntimeError):
                await person_tools._fetch_recent_emails(uuid4(), "Marie")
        client.close.assert_awaited_once()

    async def test_upcoming_events_closes_client_on_success(self):
        from src.domains.agents.tools import person_tools

        client = _provider_client(list_events=AsyncMock(return_value={"items": []}))
        with patch.object(person_tools, "_resolve_provider_client", AsyncMock(return_value=client)):
            await person_tools._fetch_upcoming_events(uuid4(), "Marie")
        client.close.assert_awaited_once()

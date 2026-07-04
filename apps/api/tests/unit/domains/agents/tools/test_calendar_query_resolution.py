"""Tests for calendar query resolution (attendee email vs dropped free-text).

Google Calendar `q` is a weak full-text match, so the tool keeps it ONLY when it
is a reliable attendee email (a person name resolved via contacts). Any other
free-text (title / concept / category / unresolved name) is dropped so the tool
lists by the time window and the Response LLM filters the concept downstream.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.tools import calendar_tools
from src.domains.agents.tools.calendar_tools import _resolve_calendar_query_param

pytestmark = [pytest.mark.unit]


def _patch_resolver(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, str]) -> None:
    """Patch resolve_recipients_to_emails to a deterministic async stub.

    Returns the mapped value for a known person name, else the input unchanged
    (mirroring the real fail-safe: unresolved names are kept as-is).
    """

    async def _fake(runtime: Any, value: str, field: str) -> str:
        return mapping.get(value, value)

    monkeypatch.setattr(calendar_tools, "resolve_recipients_to_emails", _fake)


@pytest.mark.parametrize("query", [None, "", "   "])
async def test_empty_query_returns_none(query: str | None) -> None:
    assert await _resolve_calendar_query_param(None, query) is None


async def test_semantic_category_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A category word resolves to nothing → dropped (list-and-filter)."""
    _patch_resolver(monkeypatch, {})  # nothing resolves
    assert await _resolve_calendar_query_param(None, "médical") is None


async def test_literal_phrase_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """An accent-fragile literal phrase resolves to nothing → dropped."""
    _patch_resolver(monkeypatch, {})
    assert await _resolve_calendar_query_param(None, "hotel particulier") is None


async def test_existing_email_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    """An email address is a reliable attendee filter → kept, no resolution."""
    _patch_resolver(monkeypatch, {})
    assert await _resolve_calendar_query_param(None, "jane@example.com") == "jane@example.com"


async def test_person_name_resolved_rfc5322(monkeypatch: pytest.MonkeyPatch) -> None:
    """A person name resolving to 'Name <email>' → the extracted email is kept."""
    _patch_resolver(monkeypatch, {"Jean Dupont": "Jean Dupont <jean@example.com>"})
    assert await _resolve_calendar_query_param(None, "Jean Dupont") == "jean@example.com"


async def test_person_name_resolved_plain_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """A person name resolving to a bare email → kept."""
    _patch_resolver(monkeypatch, {"Jean Dupont": "jean@example.com"})
    assert await _resolve_calendar_query_param(None, "Jean Dupont") == "jean@example.com"


async def test_unresolved_person_name_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unresolved name (no matching contact) → dropped, list-and-filter."""
    _patch_resolver(monkeypatch, {})  # 'Xavier' stays 'Xavier'
    assert await _resolve_calendar_query_param(None, "Xavier") is None

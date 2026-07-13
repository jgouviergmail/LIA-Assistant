"""Unit tests for the place_phone_call tool logic (P3.3).

Targets the pure orchestration helper ``_build_place_phone_call_output`` with the
connector guard and contact resolution mocked, plus the phone/name heuristics.
The LangChain decorator plumbing is intentionally not exercised here.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

import src.domains.agents.tools.telephony_tools as tmod
from src.domains.agents.tools.telephony_tools import (
    _build_place_phone_call_output,
    _looks_like_phone,
    _normalize_phone,
)


def _patch_connector(monkeypatch: pytest.MonkeyPatch, *, active: bool) -> None:
    async def _active(_user_id) -> bool:
        return active

    monkeypatch.setattr(tmod, "_telephony_connector_active", _active)


def _patch_search(monkeypatch: pytest.MonkeyPatch, candidates, first_match_name) -> None:
    async def _search(_user_id, _query, max_results=5):
        return candidates, first_match_name

    monkeypatch.setattr(tmod, "_search_contacts_with_phones", _search)


@pytest.mark.unit
@pytest.mark.parametrize(
    "value,expected",
    [
        ("+33612345678", True),
        ("+33 6 12 34 56 78", True),
        ("0612345678", True),
        ("Marie", False),
        ("my brother", False),
        ("", False),
    ],
)
def test_looks_like_phone(value: str, expected: bool) -> None:
    assert _looks_like_phone(value) is expected


@pytest.mark.unit
def test_normalize_phone_keeps_plus_and_digits() -> None:
    assert _normalize_phone("+33 6 12-34.56 78") == "+33612345678"
    assert _normalize_phone("06 12 34 56 78") == "0612345678"


@pytest.mark.unit
async def test_no_connector_returns_activation_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_connector(monkeypatch, active=False)
    out = await _build_place_phone_call_output(
        user_id=uuid4(), locale="fr", contact="Marie", objective="dispo mardi", date_window=None
    )
    assert out.success is False
    assert out.error_code == "telephony_not_configured"
    assert "connecteur" in out.message.lower()


@pytest.mark.unit
async def test_resolvable_contact_returns_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_connector(monkeypatch, active=True)
    _patch_search(monkeypatch, [("Marie Dupont", "+33612345678")], "Marie Dupont")

    out = await _build_place_phone_call_output(
        user_id=uuid4(),
        locale="fr",
        contact="Marie",
        objective="Lui demander si elle est libre mardi soir",
        date_window="cette semaine",
    )

    assert out.success is True
    item = next(iter(out.registry_updates.values()))
    assert item.payload["draft_type"] == "phone_call"
    assert item.payload["requires_confirmation"] is True
    content = item.payload["content"]
    assert content["callee_name"] == "Marie Dupont"
    assert content["callee_phone"] == "+33612345678"
    assert content["objective"] == "Lui demander si elle est libre mardi soir"
    assert content["date_window"] == "cette semaine"


@pytest.mark.unit
async def test_raw_number_bypasses_contact_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_connector(monkeypatch, active=True)

    async def _boom(*args, **kwargs):  # must NOT be called for a raw number
        raise AssertionError("contact resolution should be skipped for a raw number")

    monkeypatch.setattr(tmod, "_search_contacts_with_phones", _boom)

    out = await _build_place_phone_call_output(
        user_id=uuid4(),
        locale="en",
        contact="+33 6 12 34 56 78",
        objective="ask about dinner",
        date_window=None,
    )
    assert out.success is True
    content = next(iter(out.registry_updates.values())).payload["content"]
    assert content["callee_phone"] == "+33612345678"


@pytest.mark.unit
async def test_ambiguous_contact_returns_clarification(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_connector(monkeypatch, active=True)
    _patch_search(
        monkeypatch,
        [("Marie Dupont", "+33611111111"), ("Marie Durand", "+33622222222")],
        "Marie Dupont",
    )
    out = await _build_place_phone_call_output(
        user_id=uuid4(), locale="fr", contact="Marie", objective="dispo", date_window=None
    )
    assert out.success is False
    assert out.error_code == "contact_ambiguous"
    assert "Marie Dupont" in out.message and "Marie Durand" in out.message


@pytest.mark.unit
async def test_contact_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_connector(monkeypatch, active=True)
    _patch_search(monkeypatch, [], None)
    out = await _build_place_phone_call_output(
        user_id=uuid4(), locale="fr", contact="Zorglub", objective="dispo", date_window=None
    )
    assert out.success is False
    assert out.error_code == "contact_not_found"
    assert "Zorglub" in out.message


@pytest.mark.unit
async def test_contact_matched_but_no_phone(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_connector(monkeypatch, active=True)
    _patch_search(monkeypatch, [], "Marie Dupont")
    out = await _build_place_phone_call_output(
        user_id=uuid4(), locale="fr", contact="Marie", objective="dispo", date_window=None
    )
    assert out.success is False
    assert out.error_code == "contact_no_phone"
    assert "Marie Dupont" in out.message

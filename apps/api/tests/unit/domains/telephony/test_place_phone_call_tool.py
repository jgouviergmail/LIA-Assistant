"""Unit tests for the place_phone_call tool logic (P3.3).

Targets the pure orchestration helper ``_build_place_phone_call_output`` with the
connector guard and contact resolution mocked, plus the phone/name heuristics.
The LangChain decorator plumbing is intentionally not exercised here.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

import src.domains.agents.tools.telephony_tools as tmod
from src.core.config import settings
from src.domains.agents.tools.telephony_tools import (
    _build_place_phone_call_output,
    _extract_candidates,
    _looks_like_phone,
    _normalize_phone,
    _person_first_phone,
    _resolve_callee,
    _strip_trailing_annotations,
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
def test_normalize_phone_keeps_plus_and_digits(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pin the deployment knob: this test asserts the WITHOUT-country-code
    # behavior and must not depend on the ambient .env value.
    monkeypatch.setattr(settings, "telephony_default_country_code", "", raising=False)
    assert _normalize_phone("+33 6 12-34.56 78") == "+33612345678"
    assert _normalize_phone("06 12 34 56 78") == "0612345678"


@pytest.mark.unit
def test_normalize_phone_applies_default_country_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """A national number (single leading 0) gains the configured E.164 prefix."""
    monkeypatch.setattr(settings, "telephony_default_country_code", "+33", raising=False)
    assert _normalize_phone("06.82.51.16.39") == "+33682511639"
    # International forms are never rewritten
    assert _normalize_phone("0033682511639") == "0033682511639"
    assert _normalize_phone("+33682511639") == "+33682511639"
    # Too short to be a national subscriber number (short codes stay untouched,
    # even 0-leading ones — the length guard)
    assert _normalize_phone("3631") == "3631"
    assert _normalize_phone("08000") == "08000"


@pytest.mark.unit
def test_normalize_phone_without_country_code_keeps_national(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telephony_default_country_code", "", raising=False)
    assert _normalize_phone("06.82.51.16.39") == "0682511639"


@pytest.mark.unit
def test_strip_trailing_annotations() -> None:
    assert _strip_trailing_annotations("Hua Gouvier (my wife)") == "Hua Gouvier"
    assert _strip_trailing_annotations("X (a) (b)") == "X"
    assert _strip_trailing_annotations("(only annotation)") == ""
    assert _strip_trailing_annotations("Jean Dupont") == "Jean Dupont"


@pytest.mark.unit
def test_person_first_phone_prefers_canonical_form() -> None:
    """canonicalForm is E.164 — always preferred over display formatting."""
    person = {"phoneNumbers": [{"value": "06 82 51 16 39", "canonicalForm": "+33682511639"}]}
    assert _person_first_phone(person) == "+33682511639"


@pytest.mark.unit
def test_person_first_phone_normalizes_display_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without canonicalForm the display value is normalized (never spaces/dots)."""
    monkeypatch.setattr(settings, "telephony_default_country_code", "", raising=False)
    person = {"phoneNumbers": [{"value": "06 82 51 16 39"}]}
    assert _person_first_phone(person) == "0682511639"
    assert _person_first_phone({"phoneNumbers": []}) == ""


@pytest.mark.unit
def test_extract_candidates_unwraps_person_wrapper() -> None:
    """Real provider shape: hits wrapped as {'person': {...}} (all 3 providers).

    Regression for the 2026-07-17 bug: the wrapper was parsed as the person, so
    every name resolution ended 'no_phone' although the contact had a number.
    """
    payload = {
        "results": [
            {
                "person": {
                    "names": [{"displayName": "Jérôme Gouvier"}],
                    "phoneNumbers": [{"value": "06 82 51 16 39", "canonicalForm": "+33682511639"}],
                }
            }
        ],
        "totalItems": 1,
    }
    candidates, first_name = _extract_candidates(payload)
    assert first_name == "Jérôme Gouvier"
    assert candidates == [("Jérôme Gouvier", "+33682511639")]


@pytest.mark.unit
def test_extract_candidates_tolerates_unwrapped_person() -> None:
    payload = {"results": [{"names": [{"displayName": "Marie"}], "phoneNumbers": []}]}
    candidates, first_name = _extract_candidates(payload)
    assert first_name == "Marie"
    assert candidates == []  # matched but carries no phone


@pytest.mark.unit
async def test_resolve_callee_retries_with_stripped_annotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM-annotated names ('Hua Gouvier (my wife)') fall back to the clean name."""
    queries: list[str] = []

    async def _search(_user_id, query, max_results=5):
        queries.append(query)
        if query == "Hua Gouvier":
            return [("Hua Gouvier", "+33612345678")], "Hua Gouvier"
        return [], None

    monkeypatch.setattr(tmod, "_search_contacts_with_phones", _search)
    resolution = await _resolve_callee(uuid4(), "Hua Gouvier (my wife)")
    assert resolution.kind == "resolved"
    assert resolution.phone == "+33612345678"
    assert queries == ["Hua Gouvier (my wife)", "Hua Gouvier"]


@pytest.mark.unit
async def test_resolve_callee_exact_first_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A contact legitimately named with a parenthetical matches exact-first."""
    queries: list[str] = []

    async def _search(_user_id, query, max_results=5):
        queries.append(query)
        return [("Jean Dupont (plombier)", "+33698765432")], "Jean Dupont (plombier)"

    monkeypatch.setattr(tmod, "_search_contacts_with_phones", _search)
    resolution = await _resolve_callee(uuid4(), "Jean Dupont (plombier)")
    assert resolution.kind == "resolved"
    assert queries == ["Jean Dupont (plombier)"]


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

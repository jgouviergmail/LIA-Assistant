"""A shown item designated by WHAT it is is resolved by code (ADR-367).

Production 2026-10-29: after « my last 5 emails », « reply to jerome's email »
re-searched the mailbox (``from:jerome``, ``max_results=1``) and drafted a
reply to a message the person had never been shown. The description now
resolves against the items the last answers SHOWED — what each answer
declared it presented (``context/shown_items.py``) — and the person is asked
when several fit.
"""

from __future__ import annotations

from typing import Any

import pytest
from prometheus_client import REGISTRY

from src.core.config import settings
from src.domains.agents.context.registry import ContextTypeRegistry
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.services import descriptive_reference as module
from src.domains.agents.services.analysis.query_analysis_schemas import ContextReferenceOutput
from src.domains.agents.services.descriptive_reference import (
    candidate_label,
    render_shown_items,
    resolve_descriptive_reference,
)
from src.domains.agents.tools import (  # noqa: F401 — register types
    calendar_tools,
    drive_tools,
    emails_tools,
)

pytestmark = pytest.mark.unit


def _email(item_id: str, sender: str, subject: str, *, turn: int, received: int) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "EMAIL",
        "payload": {
            "id": item_id,
            "from": sender,
            "subject": subject,
            "to": "me@example.net",
            "snippet": "…",
            "internalDate": str(received),
        },
        "meta": {"source": "gmail", "domain": "emails", "turn_id": turn},
    }


def _event(item_id: str, summary: str, *, turn: int) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "EVENT",
        "payload": {"id": item_id, "summary": summary, "attendees": []},
        "meta": {"source": "google_calendar", "domain": "events", "turn_id": turn},
    }


def _state(*items: dict[str, Any], turn: int = 2) -> dict[str, Any]:
    """The registry, and the answer of each item's turn SHOWING it (in order)."""
    shown: dict[int, list[str]] = {}
    for item in items:
        if isinstance(item["meta"]["turn_id"], int):
            shown.setdefault(item["meta"]["turn_id"], []).append(item["id"])
    return {
        "current_turn_id": turn,
        "registry": {item["id"]: item for item in items},
        "shown_items": [{"turn_id": t, "ids": ids} for t, ids in sorted(shown.items())],
    }


INBOX = (
    _email("e1", '"Jérôme G" <jg@example.com>', "Photos", turn=1, received=5),
    _email("e2", "PLAUD.AI <no-reply@plaud.example>", "Weekly", turn=1, received=4),
    _email("e3", '"Jérôme G" <jg@example.com>', "Facture", turn=1, received=3),
)


def _ref(descriptor: str, domain: str = "email", selection: str = "one") -> ContextReferenceOutput:
    return ContextReferenceOutput(
        has_reference=True,
        reference_type="descriptive",
        descriptor=descriptor,
        reference_domain=domain,
        selection=selection,
    )


@pytest.fixture(autouse=True)
def _followed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "turn_follows_the_conversation", lambda: True)


def _count(outcome: str) -> float:
    return (
        REGISTRY.get_sample_value("context_descriptive_reference_total", {"outcome": outcome})
        or 0.0
    )


class TestTheShownItemADescriptionDesignates:
    def test_one_fitting_item_is_resolved(self) -> None:
        before = _count("resolved")
        resolved = resolve_descriptive_reference(_ref("plaud"), _state(*INBOX))

        assert [item["id"] for item in resolved.items] == ["e2"]
        assert resolved.candidates == []
        assert resolved.method == "descriptive"
        assert resolved.source_domain == "email"
        assert resolved.source_turn_id == 1
        assert _count("resolved") == before + 1

    def test_several_fitting_items_become_the_question(self) -> None:
        resolved = resolve_descriptive_reference(_ref("jerome"), _state(*INBOX))

        assert resolved.items == []
        assert [item["id"] for item in resolved.candidates] == ["e1", "e3"]
        assert resolved.method == "descriptive_ambiguous"
        assert resolved.descriptor == "jerome"  # what the question asks about

    def test_the_question_offers_at_most_the_configured_candidates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "entity_resolution_max_candidates", 1)
        resolved = resolve_descriptive_reference(_ref("jerome"), _state(*INBOX))

        assert [item["id"] for item in resolved.candidates] == ["e1"]

    def test_the_latest_email_is_the_newest_received(self) -> None:
        resolved = resolve_descriptive_reference(_ref("jerome", selection="latest"), _state(*INBOX))

        assert [item["id"] for item in resolved.items] == ["e1"]
        assert resolved.method == "descriptive_latest"

    def test_latest_without_a_received_date_still_asks(self) -> None:
        events = (_event("v1", "Réunion Marc", turn=1), _event("v2", "Déjeuner Marc", turn=1))
        resolved = resolve_descriptive_reference(
            _ref("Marc", domain="event", selection="latest"), _state(*events)
        )

        assert resolved.items == []
        assert [item["id"] for item in resolved.candidates] == ["v1", "v2"]

    def test_a_description_no_shown_item_fits_is_a_new_lookup(self) -> None:
        resolved = resolve_descriptive_reference(_ref("Paul"), _state(*INBOX))

        assert resolved.items == [] and resolved.candidates == []
        assert resolved.method == "descriptive_no_match"


class TestWhatCountsAsShown:
    def test_an_item_older_than_the_window_is_not_designated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "entity_resolution_max_turn_age", 3)
        old = _email("e9", "PLAUD.AI <p@plaud.example>", "Old", turn=1, received=1)

        assert resolve_descriptive_reference(_ref("plaud"), _state(old, turn=4)).items
        resolved = resolve_descriptive_reference(_ref("plaud"), _state(old, turn=5))
        assert resolved.items == [] and resolved.method == "descriptive_nothing_shown"

    def test_another_domain_is_not_designated(self) -> None:
        resolved = resolve_descriptive_reference(_ref("Photos", domain="event"), _state(*INBOX))
        assert resolved.method == "descriptive_nothing_shown"

    def test_an_item_no_answer_showed_is_not_designated(self) -> None:
        unshown = _email("e7", "PLAUD.AI <p@plaud.example>", "W", turn=1, received=1)
        unshown["meta"]["turn_id"] = None
        assert resolve_descriptive_reference(_ref("plaud"), _state(unshown)).items == []

    def test_an_item_a_turn_fetched_but_its_answer_left_out_is_not_designated(self) -> None:
        # The lookup of turn 1 also returned a Plaud mail; the answer presented the
        # two Jérôme mails alone. Stamped with turn 1 in the registry, never shown.
        state = _state(*INBOX)
        state["shown_items"] = [{"turn_id": 1, "ids": ["e1", "e3"]}]

        resolved = resolve_descriptive_reference(_ref("plaud"), state)

        assert resolved.items == [] and resolved.method == "descriptive_no_match"
        assert "Weekly" not in render_shown_items(state)

    def test_a_registry_item_object_reads_like_its_checkpointed_dict(self) -> None:
        item = RegistryItem(
            id="e5",
            type=RegistryItemType.EMAIL,
            payload={"id": "e5", "from": "PLAUD.AI <p@plaud.example>", "subject": "W"},
            meta=RegistryItemMeta(source="gmail", domain="emails", turn_id=1),
        )
        state = {
            "current_turn_id": 2,
            "registry": {"e5": item},
            "shown_items": [{"turn_id": 1, "ids": ["e5"]}],
        }
        assert [i["id"] for i in resolve_descriptive_reference(_ref("plaud"), state).items] == [
            "e5"
        ]

    def test_an_unknown_domain_designates_nothing(self) -> None:
        resolved = resolve_descriptive_reference(_ref("x", domain="spaceship"), _state(*INBOX))
        assert resolved.items == [] and resolved.candidates == []


class TestWhenNothingIsResolved:
    def test_a_turn_the_person_does_not_follow_resolves_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A routine, a ticket, a relayed call: the chat's list is not theirs.
        monkeypatch.setattr(module, "turn_follows_the_conversation", lambda: False)
        resolved = resolve_descriptive_reference(_ref("plaud"), _state(*INBOX))

        assert resolved.items == [] and resolved.candidates == []
        assert resolved.method == "descriptive_not_followed"

    def test_the_switch_off_plans_a_new_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "entity_resolution_enabled", False)
        resolved = resolve_descriptive_reference(_ref("plaud"), _state(*INBOX))

        assert resolved.items == [] and resolved.method == "descriptive_disabled"


class TestWhatTheAnalyzerIsShown:
    def test_each_shown_item_is_one_line_of_its_identity(self) -> None:
        lines = render_shown_items(_state(*INBOX)).splitlines()

        assert lines[0] == '- [email] "Jérôme G" <jg@example.com> · Photos · me@example.net'
        assert len(lines) == 3

    def test_the_newest_answer_comes_first_and_the_cap_holds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "entity_resolution_shown_items_max", 2)
        older = _event("v1", "Dentiste", turn=1)
        newer = _email("e4", "Acme <a@acme.example>", "Notes", turn=2, received=9)
        lines = render_shown_items(_state(older, newer, *INBOX[:1], turn=3)).splitlines()

        assert lines == [
            "- [email] Acme <a@acme.example> · Notes · me@example.net",
            "- [event] Dentiste",
        ]

    def test_a_long_or_multiline_value_stays_on_one_bounded_line(self) -> None:
        noisy = _email("e6", "X <x@example.com>", "a\nb " + "z" * 300, turn=1, received=1)
        (line,) = render_shown_items(_state(noisy)).splitlines()

        assert "\n" not in line and len(line) <= module.SHOWN_LINE_MAX_CHARS

    def test_nothing_is_shown_to_a_turn_the_person_does_not_follow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(module, "turn_follows_the_conversation", lambda: False)
        assert render_shown_items(_state(*INBOX)) == ""

    def test_nothing_shown_renders_nothing(self) -> None:
        assert render_shown_items({"current_turn_id": 1, "registry": {}}) == ""
        assert ContextTypeRegistry.get_definition("emails") is not None


class TestTheOptionsOfTheQuestion:
    def test_an_option_shows_what_tells_it_apart(self) -> None:
        payload = {
            **INBOX[0]["payload"],
            "date_formatted": "mardi 15 septembre 2026 à 17:24",
        }
        label = candidate_label(payload, ContextTypeRegistry.get_definition("emails"))

        # Sender, subject, date — not the recipient every option shares.
        assert label == '"Jérôme G" <jg@example.com> · Photos · mardi 15 septembre 2026 à 17:24'

    def test_a_type_declaring_none_shows_its_identity(self) -> None:
        payload = {"id": "f1", "name": "Devis cuisine.pdf", "mimeType": "application/pdf"}
        assert candidate_label(payload, ContextTypeRegistry.get_definition("files")) == (
            "Devis cuisine.pdf"
        )

    def test_an_option_is_one_bounded_line(self) -> None:
        payload = {"from": "X <x@example.com>", "subject": "a\nb " + "z" * 300}
        label = candidate_label(payload, ContextTypeRegistry.get_definition("emails"))
        assert "\n" not in label and len(label) <= module.CANDIDATE_LINE_MAX_CHARS

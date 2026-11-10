"""The portrait measurement corpus is complete, invented and sized as declared."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

CORPUS = Path(__file__).resolve().parents[3] / "scripts" / "journals" / "portrait_corpus.json"


def _corpus() -> dict[str, Any]:
    return json.loads(CORPUS.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_corpus_holds_every_source_at_its_declared_size() -> None:
    corpus = _corpus()
    assert corpus["language"] == "fr"
    assert len(corpus["memories"]) == 60
    assert len(corpus["interests"]) == 20
    assert len(corpus["habits"]["recurring"]) == 2
    assert len(corpus["journal_entries"]) == 45
    assert len(corpus["relation_debriefs"]) == 3
    assert len(corpus["open_loops"]) == 4
    assert len(corpus["workboard"]) == 4
    assert len(corpus["routines"]) == 3
    assert len(corpus["reminders"]) == 3
    assert len(corpus["bookmarks"]) == 3


def test_journal_entries_cover_the_eligibility_classes() -> None:
    entries = _corpus()["journal_entries"]
    levels = {(e["level"], e["confidence"], e["contradiction_count"] > 0) for e in entries}
    assert ("L0", "low", False) in levels
    assert ("L1", "medium", False) in levels
    assert ("L1", "medium", True) in levels
    assert ("L2", "medium", False) in levels
    assert ("L3", "high", False) in levels
    assert all(len(e["content"]) <= 800 for e in entries)
    assert all(len(m["content"]) <= 400 for m in _corpus()["memories"])


def test_the_corpus_names_people_by_a_first_name_alone_and_carries_no_contact_detail() -> None:
    # Invented, and checked structurally — never against a list of real names or
    # places, which would write them into the repository.
    corpus = _corpus()
    corpus.pop("timezone")  # an IANA zone names a city by construction
    for debrief in corpus["relation_debriefs"]:
        assert len(debrief["display_name"].split()) == 1
    text = json.dumps(corpus, ensure_ascii=False)
    assert "@" not in text
    assert re.search(r"\b\d{5}\b", text) is None  # a postcode
    assert re.search(r"(?:\+|\b0)\d[\d .-]{8,}\d", text) is None  # a phone number


def test_the_recurring_needs_are_what_the_nightly_recompute_writes() -> None:
    """ADR-375: the seeded rows go through ``need_payload`` and must read back
    under the v2 contract, on a registered domain, with an analyzer intent —
    a persona the producer could never write measures nothing."""
    from datetime import date

    from src.domains.agents.analysis.query_intelligence import IMMEDIATE_INTENTS
    from src.domains.habits.discussion_projection import RecurringPayload
    from src.domains.habits.need_domains import NEED_DOMAINS
    from src.domains.habits.needs import Need, need_payload

    for entry in _corpus()["habits"]["recurring"]:
        assert entry["key"] in NEED_DOMAINS
        assert entry["usual_intent"] in IMMEDIATE_INTENTS
        need = Need(
            domain=entry["key"],
            cadence=entry["cadence"],
            weekday=entry["weekday"],
            usual_hour=entry["usual_hour"],
            prefill_hour=entry["usual_hour"],
            part_of_day=entry["part_of_day"],
            distinct_days=5,
            active_days=20,
            occurrences=5,
            at_automation_bar=True,
            last_day=date(2026, 11, 8),
        )
        RecurringPayload.model_validate(need_payload(need, usual_intent=entry["usual_intent"]))

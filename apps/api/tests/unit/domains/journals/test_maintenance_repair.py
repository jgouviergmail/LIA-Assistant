"""An abstraction its supports cannot carry is repaired, never the paid batch refused.

Measured 2026-10-12 c: one synthesis citing immature rules voided a whole paid
consolidation — its maintenance AND its portrait (2 runs of 8 on the measurement
persona). The level is metadata the evidence decides (ADR-184), exactly like the
confidence `_confidence` already lowers instead of refusing: the action is applied
at the level its supports carry, and the batch goes on.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from structlog.testing import capture_logs

from src.domains.journals.consolidation_output import parse_maintenance_output
from src.domains.journals.maintenance_actions import repair_maintenance, validate_maintenance

pytestmark = pytest.mark.unit


def _entry(
    content: str, *, level: str = "L1", confidence: str = "medium", theme: str = "learnings"
):
    return SimpleNamespace(
        id=uuid4(),
        title="Rule",
        content=content,
        level=level,
        confidence=confidence,
        contradiction_count=0,
        theme=theme,
        revision=1,
        evidence_count=0,
        search_hints=None,
    )


def _parse(*actions: dict) -> object:
    output = parse_maintenance_output(json.dumps({"actions": list(actions)}))
    assert output.valid, output.error
    return output


def _synthesis(supports: list, *, level: str = "L2") -> dict:
    return {
        "action": "create",
        "theme": "user_observations",
        "title": "Durable synthesis",
        "content": "Across contexts, the user decides on evidence first.",
        "level": level,
        "confidence": "high",
        "support_ids": [str(entry.id) for entry in supports],
    }


def test_a_synthesis_on_immature_rules_is_created_at_l1_and_the_batch_validates():
    first = _entry("WHEN deciding -> DO ask for the figure first.")
    second = _entry("WHEN reporting -> DO cite the source.")
    entries = [first, second]
    output = _parse(_synthesis(entries))
    with pytest.raises(ValueError, match="independently mature"):
        validate_maintenance(output, entries, 800)

    repaired = repair_maintenance(output, entries)

    action = repaired.actions[0]
    assert action.level is not None and action.level.value == "L1"
    assert action.support_ids == []
    assert action.content == "Across contexts, the user decides on evidence first."
    validate_maintenance(repaired, entries, 800)


def test_a_promotion_its_supports_cannot_carry_keeps_the_entry_at_its_level():
    rule = _entry("WHEN planning -> DO offer two options.")
    output = _parse(
        {"action": "update", "entry_id": str(rule.id), "level": "L2", "mood": "curious"}
    )

    repaired = repair_maintenance(output, [rule])

    action = repaired.actions[0]
    assert action.level is None  # the entry keeps L1: no level change is applied
    assert action.mood is not None and action.mood.value == "curious"
    validate_maintenance(repaired, [rule], 800)


def test_an_l1_rewrite_asked_at_l2_keeps_its_words_at_l1():
    rule = _entry("Planning goes better with options.")
    output = _parse(
        {
            "action": "update",
            "entry_id": str(rule.id),
            "content": "WHEN planning -> DO offer two options BECAUSE the user compares.",
            "level": "L2",
        }
    )

    repaired = repair_maintenance(output, [rule])

    action = repaired.actions[0]
    assert action.level is None
    assert action.content == "WHEN planning -> DO offer two options BECAUSE the user compares."
    validate_maintenance(repaired, [rule], 800)


def test_a_rewrite_of_a_validated_abstraction_without_supports_keeps_its_words():
    # Step 3 asks for reformats; an L2's words were validated by their supports, so a
    # rewrite citing none is not applied — the other fields of the action are.
    pattern = _entry(
        "Across contexts the user wants evidence first.", level="L2", confidence="high"
    )
    output = _parse(
        {
            "action": "update",
            "entry_id": str(pattern.id),
            "title": "Evidence first",
            "content": "WHEN any decision -> DO lead with the evidence BECAUSE trust.",
            "search_hints": ["evidence"],
        }
    )

    repaired = repair_maintenance(output, [pattern])

    action = repaired.actions[0]
    assert action.content is None and action.title is None
    assert action.search_hints == ["evidence"]
    validate_maintenance(repaired, [pattern], 800)


def test_a_supported_abstraction_is_left_exactly_as_proposed():
    first = _entry("WHEN deciding -> DO ask for the figure first.", confidence="high")
    second = _entry("WHEN reporting -> DO cite the source.", confidence="high")
    entries = [first, second]
    output = _parse(_synthesis(entries))

    repaired = repair_maintenance(output, entries)

    assert repaired.actions == output.actions
    validate_maintenance(repaired, entries, 800)


def test_a_support_the_batch_changes_cannot_carry_the_abstraction_either():
    first = _entry("WHEN preparing -> DO compare alternatives.", confidence="high")
    second = _entry("WHEN finalizing -> DO verify the result.", confidence="high")
    entries = [first, second]
    output = _parse(
        {"action": "update", "entry_id": str(first.id), "mood": "curious"},
        _synthesis(entries),
    )

    repaired = repair_maintenance(output, entries)

    assert repaired.actions[1].level is not None and repaired.actions[1].level.value == "L1"
    validate_maintenance(repaired, entries, 800)


def test_an_l3_on_immature_rules_is_created_at_l1():
    first = _entry("WHEN deciding -> DO ask for the figure first.")
    second = _entry("WHEN reporting -> DO cite the source.")
    entries = [first, second]
    output = _parse(_synthesis(entries, level="L3"))

    repaired = repair_maintenance(output, entries)

    assert repaired.actions[0].level is not None and repaired.actions[0].level.value == "L1"
    validate_maintenance(repaired, entries, 800)


def test_the_identity_rule_is_not_a_level_repair_and_still_refuses():
    # A method lesson filed as an L3 identity facet is another refusal, kept as is.
    facet = _entry("The user's durable preference.", level="L3", theme="user_observations")
    output = _parse({"action": "update", "entry_id": str(facet.id), "theme": "learnings"})

    repaired = repair_maintenance(output, [facet])

    assert repaired.actions == output.actions
    with pytest.raises(ValueError, match="identity facets"):
        validate_maintenance(repaired, [facet], 800)


def test_every_repair_is_counted_and_logged_without_content():
    first = _entry("WHEN deciding -> DO ask for the figure first.")
    second = _entry("WHEN reporting -> DO cite the source.")
    pattern = _entry(
        "Across contexts the user wants evidence first.", level="L2", confidence="high"
    )
    entries = [first, second, pattern]
    output = _parse(
        _synthesis([first, second]),
        {"action": "update", "entry_id": str(pattern.id), "content": "Rewritten pattern."},
    )

    with capture_logs() as logs:
        repair_maintenance(output, entries)

    [line] = [log for log in logs if log["event"] == "journal_maintenance_abstractions_repaired"]
    assert line["repaired"] == 2
    assert (line["created_at_l1"], line["level_kept"], line["words_kept"]) == (1, 0, 1)
    assert "Rewritten" not in json.dumps(line, default=str)


def test_nothing_is_logged_when_nothing_needs_repair():
    rule = _entry("WHEN planning -> DO offer two options.")
    output = _parse({"action": "update", "entry_id": str(rule.id), "mood": "curious"})

    with capture_logs() as logs:
        repaired = repair_maintenance(output, [rule])

    assert repaired is output
    assert not [log for log in logs if log["event"] == "journal_maintenance_abstractions_repaired"]


def test_an_update_naming_an_unknown_entry_is_not_repaired_and_still_refused():
    first = _entry("WHEN deciding -> DO ask for the figure first.")
    output = _parse({"action": "update", "entry_id": str(uuid4()), "level": "L2"})

    repaired = repair_maintenance(output, [first])

    assert repaired is output
    with pytest.raises(ValueError, match="unknown maintenance entry"):
        validate_maintenance(repaired, [first], 800)

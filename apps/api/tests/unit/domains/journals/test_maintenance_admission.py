"""Maintenance actions are admitted one by one, like the portrait claims (2026-10-13).

Measured: one unreadable or refused action voided a whole paid consolidation — its other
actions AND its portrait — three times in eleven runs on the measurement persona (a
support cited by its portrait id instead of its entry id, a synthesis on immature rules).
An action that cannot be read or applied is dropped and counted, together with every
action naming the same entry; the rest proceeds. An answer of actions alone, all of them
refused, is still invalid: nothing of it can be used.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from structlog.testing import capture_logs

from src.domains.journals.consolidation_output import parse_maintenance_output
from src.domains.journals.maintenance_actions import admit_maintenance, validate_maintenance

pytestmark = pytest.mark.unit


def _entry(content: str = "WHEN planning -> DO offer two options.", **fields):
    values = {
        "id": uuid4(),
        "title": "Rule",
        "content": content,
        "level": "L1",
        "confidence": "medium",
        "contradiction_count": 0,
        "theme": "learnings",
        "revision": 1,
        "evidence_count": 0,
        "search_hints": None,
    }
    return SimpleNamespace(**{**values, **fields})


def _claim(entry) -> dict:
    return {
        "facet": "interaction",
        "text": "Une lecture qui croise plusieurs observations sans en recopier une seule.",
        "supports": [{"source": f"journal:{entry.id}", "quote": entry.content}],
        "placement": "full",
    }


def _parse(actions: list[dict], claims: list[dict] | None = None):
    payload: dict = {"actions": actions}
    if claims is not None:
        payload["portrait_claims"] = claims
    return parse_maintenance_output(json.dumps(payload))


# --- reading: an unreadable action is rejected alone ------------------------------------


def test_the_measured_portrait_id_in_support_ids_rejects_that_action_alone():
    kept, synthesised = _entry(), _entry("WHEN reporting -> DO cite the source.")
    output = _parse(
        [
            {"action": "update", "entry_id": str(kept.id), "title": "Options"},
            {
                "action": "update",
                "entry_id": str(synthesised.id),
                "level": "L2",
                "support_ids": ["pi_" + "a" * 64, str(kept.id)],
            },
        ],
        [_claim(kept)],
    )

    assert output.valid
    assert [action.entry_id for action in output.actions] == [str(kept.id)]
    [rejected] = output.rejected_actions
    assert rejected["action_index"] == 1 and rejected["codes"] == ["uuid_parsing"]
    assert len(output.portrait_claims or []) == 1


def test_an_action_whose_fields_do_not_belong_to_it_is_rejected_alone():
    kept = _entry()
    output = _parse(
        [
            {"action": "delete", "entry_id": str(uuid4()), "content": "not deleted content"},
            {"action": "update", "entry_id": str(kept.id), "title": "Options"},
        ]
    )

    assert output.valid and len(output.actions) == 1
    [rejected] = output.rejected_actions
    assert rejected == {
        "action_index": 0,
        "reason": "delete and merge cannot carry ignored mutation fields",
    }


def test_every_action_naming_a_shared_entry_is_rejected_and_the_others_kept():
    shared, other = uuid4(), _entry()
    output = _parse(
        [
            {"action": "update", "entry_id": shared.hex.upper(), "title": "first"},
            {"action": "delete", "entry_id": str(shared)},
            {"action": "update", "entry_id": str(other.id), "title": "Options"},
        ],
        [],
    )

    assert output.valid
    assert [action.entry_id for action in output.actions] == [str(other.id)]
    assert {item["action_index"] for item in output.rejected_actions} == {0, 1}
    assert {item["reason"] for item in output.rejected_actions} == {
        "entry named by several maintenance actions"
    }


def test_an_answer_of_actions_alone_all_refused_is_invalid():
    output = _parse([{"action": "create"}, {"action": "update"}])
    assert not output.valid


def test_refused_actions_beside_portrait_claims_leave_a_usable_answer():
    entry = _entry()
    output = _parse([{"action": "create"}], [_claim(entry)])
    assert output.valid and output.actions == [] and len(output.rejected_actions) == 1


def test_a_rejection_carries_codes_never_the_text_it_refused():
    output = _parse(
        [
            {"action": "create", "theme": "learnings", "title": "Secret title", "content": ""},
            {"action": "update", "entry_id": str(uuid4()), "title": "Options"},
        ]
    )
    assert "Secret" not in json.dumps(output.rejected_actions)


# --- applying: an action the snapshot refuses is dropped alone --------------------------


def test_an_action_naming_an_unknown_entry_is_dropped_and_the_rest_validates():
    known = _entry()
    output = _parse(
        [
            {"action": "update", "entry_id": str(uuid4()), "title": "Ghost"},
            {"action": "update", "entry_id": str(known.id), "title": "Options"},
        ]
    )

    admitted = admit_maintenance(output, [known], 800)

    assert [action.entry_id for action in admitted.actions] == [str(known.id)]
    assert admitted.rejected_actions[-1] == {
        "action_index": 0,
        "reason": "unknown maintenance entry",
    }
    validate_maintenance(admitted, [known], 800)


def test_the_identity_rule_drops_its_action_alone():
    facet = _entry("The user's durable preference.", level="L3", theme="user_observations")
    rule = _entry()
    output = _parse(
        [
            {"action": "update", "entry_id": str(facet.id), "theme": "learnings"},
            {"action": "update", "entry_id": str(rule.id), "title": "Options"},
        ]
    )

    admitted = admit_maintenance(output, [facet, rule], 800)

    assert [action.entry_id for action in admitted.actions] == [str(rule.id)]
    validate_maintenance(admitted, [facet, rule], 800)


def test_indices_name_the_proposal_not_the_admitted_list():
    first, second = _entry(), _entry("WHEN reporting -> DO cite the source.")
    output = _parse(
        [
            {"action": "create"},
            {"action": "update", "entry_id": str(uuid4()), "title": "Ghost"},
            {"action": "update", "entry_id": str(first.id), "title": "Options"},
            {"action": "update", "entry_id": str(second.id), "title": "Sources"},
        ]
    )

    admitted = admit_maintenance(output, [first, second], 800)

    assert sorted(item["action_index"] for item in admitted.rejected_actions) == [0, 1]
    assert len(admitted.actions) == 2


def test_every_action_refused_with_no_portrait_answer_is_still_invalid():
    output = _parse([{"action": "update", "entry_id": str(uuid4()), "title": "Ghost"}])
    with pytest.raises(ValueError, match="every maintenance action was refused"):
        admit_maintenance(output, [], 800)


def test_nothing_to_drop_returns_the_proposal_itself_and_logs_nothing():
    rule = _entry()
    output = _parse([{"action": "update", "entry_id": str(rule.id), "title": "Options"}])

    with capture_logs() as logs:
        admitted = admit_maintenance(output, [rule], 800)

    assert admitted is output
    assert not [log for log in logs if log["event"] == "journal_maintenance_actions_dropped"]


def test_every_drop_is_counted_and_logged_with_reasons_only():
    rule = _entry()
    output = _parse(
        [
            {"action": "create"},
            {"action": "update", "entry_id": str(uuid4()), "title": "Ghost"},
            {"action": "update", "entry_id": str(rule.id), "title": "Options"},
        ]
    )

    with capture_logs() as logs:
        admit_maintenance(output, [rule], 800)

    [line] = [log for log in logs if log["event"] == "journal_maintenance_actions_dropped"]
    assert (line["proposed"], line["dropped"]) == (3, 2)
    assert "unknown maintenance entry" in line["reasons"]
    assert "Ghost" not in json.dumps(line, default=str)

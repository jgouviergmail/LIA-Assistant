"""Strict complete payloads and deterministic passage publication."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.domains.journals.consolidation_output import (
    PortraitClaim,
    PortraitSupport,
    grounded_portraits,
    parse_maintenance_output,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "raw",
    [
        '{"actions":[],"actions":[]}',
        '{"actions":[],"valid":true}',
        '{"actions":[],"unknown":"ignored before"}',
        '{"actions":[],"portrait_claims":[{"facet":"interaction","text":"A natural sentence.","supports":[{"source":"habits","source":"memories","quote":"- item"}]}]}',
        '{"actions":[],"portrait_claims":[{"facet":"interaction","text":"A natural sentence.","supports":[{"source":"habits","quote":"- item"}],"explanation":"ignored"}]}',
        '{"actions":[]} trailing commentary',
        '```json\n{"actions":[]}\n```',
    ],
)
def test_ambiguous_or_noncontract_complete_payload_is_invalid(raw):
    assert not parse_maintenance_output(raw).valid


@pytest.mark.parametrize(
    "fields",
    [
        {"action": "update"},
        {"action": "update", "content": "rule", "ignored": "field"},
        {"action": "delete", "content": "not deleted content"},
        {"action": "delete", "support_ids": [str(uuid4())]},
        {"action": "merge", "merge_source_ids": [str(uuid4())], "content": "ignored rewrite"},
        {"action": "merge", "merge_source_ids": [str(uuid4())], "support_ids": [str(uuid4())]},
    ],
)
def test_fields_must_belong_to_the_requested_operation(fields):
    action = {"entry_id": str(uuid4()), **fields}
    assert not parse_maintenance_output(json.dumps({"actions": [action]})).valid


def test_duplicate_action_json_keys_do_not_select_arbitrary_last_operation():
    identifier = uuid4()
    raw = '{"actions":[{"action":"update","action":"delete",' f'"entry_id":"{identifier}"' "}]}"
    assert not parse_maintenance_output(raw).valid


def test_a_late_invalid_passage_cannot_partially_populate_published():
    entry = SimpleNamespace(
        id=uuid4(),
        content="WHEN urgent -> DO state one next action BECAUSE explicitly requested.",
        level="L1",
        confidence="medium",
        contradiction_count=0,
        theme="self_reflection",
        revision=1,
        evidence_count=0,
    )
    valid = PortraitClaim(
        facet="interaction",
        text="Pour une demande urgente, privilégier la prochaine action qu'il demande.",
        supports=[PortraitSupport(source=f"journal:{entry.id}", quote=entry.content)],
        in_brief=True,
    )
    invalid = PortraitClaim(
        facet="context",
        text="Son activité semble suivre un rythme régulier.",
        supports=[PortraitSupport(source="habits", quote="- invented habit")],
    )
    published = []
    with pytest.raises(ValueError):
        grounded_portraits([valid, invalid], [entry], {}, published=published)
    assert published == []


def test_publication_records_only_whole_claims_fitting_the_full_budget(monkeypatch):
    from src.core.config import settings

    quote = "- Explicit preference: one next step when urgently requested."
    prose = "Pour une demande urgente, il souhaite une prochaine action plutôt qu'un développement prolongé."
    claim = PortraitClaim(
        facet="interaction",
        text=prose,
        supports=[PortraitSupport(source="memories", quote=quote)],
        in_brief=True,
    )
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 100)
    monkeypatch.setattr(settings, "journal_portrait_brief_max_tokens", 1)
    published = []
    full, brief = grounded_portraits([claim], [], {"memories": quote}, published=published)
    assert full == prose and brief is None
    assert published == [claim.model_copy(update={"in_brief": False})]
    published.clear()
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 1)
    assert grounded_portraits([claim], [], {"memories": quote}, published=published) == (None, None)
    assert published == []

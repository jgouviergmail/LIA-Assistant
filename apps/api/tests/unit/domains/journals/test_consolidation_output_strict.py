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


def test_an_invalid_passage_is_dropped_and_the_valid_claims_still_publish():
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
        placement="brief",
    )
    invalid = PortraitClaim(
        facet="context",
        text="Son activité semble suivre un rythme régulier.",
        supports=[PortraitSupport(source="habits", quote="- invented habit")],
    )
    published = []
    # The invented habit proves nothing: that claim is dropped, the proven one is published.
    full, brief = grounded_portraits([valid, invalid], [entry], {}, published=published)
    assert (full, brief) == (None, valid.text)
    assert [claim.text for claim in published] == [valid.text]


def test_the_brief_is_written_from_its_own_claims_never_from_the_full(monkeypatch):
    from src.core.config import settings

    quote = "- Explicit preference: one next step when urgently requested."
    support = PortraitSupport(source="memories", quote=quote)
    full_claim = PortraitClaim(
        facet="interaction",
        text="Pour une demande urgente, il souhaite une prochaine action plutôt qu'un développement prolongé.",
        supports=[support],
    )
    brief_claim = PortraitClaim(
        facet="interaction",
        placement="brief",
        text="En urgence, une prochaine action, pas un développement.",
        supports=[support],
    )
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 400)
    monkeypatch.setattr(settings, "journal_portrait_brief_max_tokens", 70)
    published = []
    full, brief = grounded_portraits(
        [full_claim, brief_claim], [], {"memories": quote}, published=published
    )
    assert full == full_claim.text and brief == brief_claim.text
    assert [claim.placement for claim in published] == ["full", "brief"]


def test_no_brief_claims_leaves_the_brief_empty():
    quote = "- Explicit preference: one next step when urgently requested."
    claim = PortraitClaim(
        facet="interaction",
        text="Pour une demande urgente, il souhaite une prochaine action concrète.",
        supports=[PortraitSupport(source="memories", quote=quote)],
    )
    full, brief = grounded_portraits([claim], [], {"memories": quote})
    assert full == claim.text and brief is None


def test_every_proven_claim_is_published_whatever_its_size(monkeypatch):
    from src.core.config import settings

    quote = "- Explicit preference: one next step when urgently requested."
    claim = PortraitClaim(
        facet="interaction",
        placement="brief",
        text="Un résumé bien trop long pour tenir dans le budget du résumé. " * 10,
        supports=[PortraitSupport(source="memories", quote=quote)],
    )
    monkeypatch.setattr(settings, "journal_portrait_brief_max_tokens", 10)
    published = []
    # The budget is the target the prompt states, never a clamp: the synthesis is complete.
    assert grounded_portraits([claim], [], {"memories": quote}, published=published) == (
        None,
        claim.text,
    )
    assert published == [claim]


def test_a_reading_may_cite_every_item_it_rests_on_up_to_the_published_cap():
    from src.domains.journals.consolidation_output import PORTRAIT_CLAIM_SUPPORTS_MAX

    supports = [
        PortraitSupport(source="memories", item_id=f"pi_{i:04d}")
        for i in range(PORTRAIT_CLAIM_SUPPORTS_MAX)
    ]
    claim = PortraitClaim(
        facet="posture", text="Une lecture fondée sur beaucoup.", supports=supports
    )
    assert len(claim.supports) == PORTRAIT_CLAIM_SUPPORTS_MAX
    with pytest.raises(ValueError):
        PortraitClaim(
            facet="posture",
            text="Une de trop.",
            supports=[*supports, PortraitSupport(source="memories", item_id="pi_more")],
        )


@pytest.mark.parametrize(
    "facet", ["posture", "focus", "context", "rhythm", "tension", "interaction", "uncertainty"]
)
def test_the_seven_analytical_facets_are_accepted(facet):
    claim = PortraitClaim(
        facet=facet,
        text="Une lecture.",
        supports=[PortraitSupport(source="memories", item_id="pi_a")],
    )
    assert claim.facet == facet
    with pytest.raises(ValueError):
        PortraitClaim(
            facet="inventory",
            text="x",
            supports=[PortraitSupport(source="memories", item_id="pi_a")],
        )


def test_an_unreadable_claim_is_rejected_alone_and_the_batch_stays_valid():
    # A claim-level fault (here an extra field) used to void the whole paid run,
    # maintenance actions included (review 2026-10-12 b): it is counted, never fatal.
    raw = (
        '{"actions":[],"portrait_claims":[{"facet":"interaction","text":"A natural sentence.",'
        '"supports":[{"source":"habits","quote":"- item"}],"explanation":"ignored"}]}'
    )
    result = parse_maintenance_output(raw)
    assert result.valid and result.portrait_claims == []
    assert result.rejected_claims == [
        {"claim_index": 0, "reason": "unreadable portrait claim", "codes": ["extra_forbidden"]}
    ]


def test_supports_past_the_cap_are_cut_and_duplicates_folded_never_the_batch_refused():
    from src.domains.journals.consolidation_output import PORTRAIT_CLAIM_SUPPORTS_MAX

    supports = [
        {"source": "memories", "item_id": f"pi_{i:04d}"}
        for i in range(PORTRAIT_CLAIM_SUPPORTS_MAX + 5)
    ]
    supports.insert(0, dict(supports[0]))  # the same item cited twice is one support
    result = parse_maintenance_output(
        json.dumps(
            {
                "actions": [],
                "portrait_claims": [
                    {"facet": "posture", "text": "Une lecture.", "supports": supports}
                ],
            }
        )
    )
    assert result.valid and result.rejected_claims == []
    assert len(result.portrait_claims[0].supports) == PORTRAIT_CLAIM_SUPPORTS_MAX
    assert result.portrait_claims[0].supports[0].item_id == "pi_0000"


def test_claims_past_the_cap_are_counted_not_fatal():
    from src.domains.journals.consolidation_output import PORTRAIT_CLAIMS_MAX

    claims = [
        {
            "facet": "focus",
            "text": f"Lecture numéro {'x' * (i + 1)}.",
            "supports": [{"source": "memories", "item_id": "pi_a"}],
        }
        for i in range(PORTRAIT_CLAIMS_MAX + 1)
    ]
    result = parse_maintenance_output(json.dumps({"actions": [], "portrait_claims": claims}))
    assert result.valid and len(result.portrait_claims) == PORTRAIT_CLAIMS_MAX
    assert result.rejected_claims == [
        {"claim_index": PORTRAIT_CLAIMS_MAX, "reason": "beyond the claims cap"}
    ]

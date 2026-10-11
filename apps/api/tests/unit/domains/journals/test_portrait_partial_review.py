"""A complete semantic verdict may retain only its individually approved facets."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from src.core.config import settings
from src.domains.journals import portrait_review as review
from src.domains.journals.consolidation_lifecycle import ConsolidationSnapshot
from src.domains.journals.consolidation_output import (
    MaintenanceOutput,
    PortraitClaim,
    PortraitSupport,
    grounded_portraits,
)
from src.domains.journals.consolidation_settlement import _publish_portrait
from src.domains.journals.portrait_catalogue import source_item_id
from src.domains.journals.portrait_sources import PortraitSourceBundle
from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter

pytestmark = pytest.mark.unit


@pytest.fixture
def seven_facets(monkeypatch):
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 1000)
    monkeypatch.setattr(settings, "journal_portrait_brief_max_tokens", 1000)
    line = "- If I ask you to delete a sensitive email, get my explicit confirmation first."
    sources = PortraitSourceBundle({"memories": line}, {"journal_entries": 0})
    paragraphs = [
        "Lorsque je dois supprimer un courriel sensible, j'attends une confirmation explicite de sa part.",
        "Son accord explicite doit précéder toute suppression de courriel sensible.",
        "Pour ses courriels sensibles, le passage à la suppression reste soumis à sa validation explicite.",
        "Il souhaite maîtriser toutes les décisions qui le concernent.",
        "La maîtrise du risque est un pilier permanent de sa personnalité.",
        "Une suppression de courriel sensible exige son aval préalable.",
        "Ce besoin de contrôle revient régulièrement dans ses demandes.",
    ]
    claims = [
        PortraitClaim(
            facet="interaction",
            text=text,
            in_brief=index in (0, 2, 5),
            supports=[PortraitSupport(source="memories", item_id=source_item_id("memories", line))],
        )
        for index, text in enumerate(paragraphs)
    ]
    output = MaintenanceOutput(valid=True, actions=[], portrait_claims=claims)
    candidate = review.prepare_portrait_review(output, [], sources)
    assert candidate is not None and len(candidate.evidence) == 7
    return output, sources, candidate


def _verdict(index, **changes):
    return {
        "index": index,
        "supported": True,
        "scope_preserved": True,
        "uncertainty_preserved": True,
        "synthesized": True,
        **changes,
    }


def _mixed_verdicts():
    return [
        _verdict(index, supported=index not in (4, 6), scope_preserved=index != 3)
        for index in range(7)
    ]


def test_complete_review_accepts_only_facets_whose_four_criteria_are_true(seven_facets):
    _, _, candidate = seven_facets
    accepted = review.approve_portrait_review(json.dumps({"reviews": _mixed_verdicts()}), candidate)
    assert accepted == (0, 1, 2, 5)


@pytest.mark.parametrize(
    "criterion", ["supported", "scope_preserved", "uncertainty_preserved", "synthesized"]
)
def test_no_failed_criterion_is_relaxed_by_selective_publication(seven_facets, criterion):
    _, _, candidate = seven_facets
    verdicts = [_verdict(index, **{criterion: index != 1}) for index in range(7)]
    accepted = review.approve_portrait_review(json.dumps({"reviews": verdicts}), candidate)
    assert accepted == (0, 2, 3, 4, 5, 6)


async def _receipt(monkeypatch, candidate, verdicts):
    monkeypatch.setattr(review, "capture_pricing_snapshot", lambda: None)
    capture = SimpleNamespace(
        get_billing_records=Mock(return_value=[]), ensure_response_record=Mock()
    )
    invoke = AsyncMock(return_value=AIMessage(content=json.dumps({"reviews": verdicts})))
    persist = AsyncMock()
    receipt = await review.review_portrait(
        candidate,
        llm=object(),
        user_id=uuid4(),
        run_id="offline-partial-review",
        configured_model="synthetic-review",
        requested_model="synthetic-review",
        capture=capture,
        invoke=invoke,
        persist=persist,
        context_window=128000,
    )
    invoke.assert_awaited_once()
    persist.assert_awaited_once()
    return receipt


async def test_selected_source_only_paragraphs_are_canonical_with_stable_brief_membership(
    seven_facets,
    monkeypatch,
):
    output, sources, candidate = seven_facets
    receipt = await _receipt(monkeypatch, candidate, _mixed_verdicts())
    review.require_portrait_review(output, [], sources, receipt)
    selected = review.reviewed_portrait(output, [], sources, receipt)
    expected = [output.portrait_claims[index] for index in (0, 1, 2, 5)]
    assert [claim.text for claim in selected.portrait_claims] == [claim.text for claim in expected]
    assert [claim.in_brief for claim in selected.portrait_claims] == [True, False, True, True]
    assert all(
        support.model_dump() == {"source": "memories", "quote": sources.sections["memories"]}
        for claim in selected.portrait_claims
        for support in claim.supports
    )
    full, brief = grounded_portraits(selected.portrait_claims, [], sources.sections)
    assert full == "\n\n".join(claim.text for claim in expected)
    assert brief == "\n\n".join(claim.text for claim in expected if claim.in_brief)
    assert len(output.portrait_claims) == 7
    assert receipt.reviewed_digest == candidate.digest
    assert receipt.approved_indices == (0, 1, 2, 5)
    assert receipt.digest != candidate.digest


async def test_budget_rebased_indices_select_admitted_claims_without_refilling_omitted_paragraphs(
    seven_facets,
    monkeypatch,
):
    output, sources, _ = seven_facets
    first, second, omitted = (output.portrait_claims[index] for index in (1, 5, 6))
    oversized = output.portrait_claims[0].model_copy(
        update={"text": output.portrait_claims[0].text * 15}
    )
    counter = OpenAITokenCounter()
    monkeypatch.setattr(
        settings,
        "journal_portrait_full_max_tokens",
        counter.count(first.text + "\n\n" + second.text, "gpt-4o"),
    )
    payload = output.model_copy(update={"portrait_claims": [oversized, first, second, omitted]})
    candidate = review.prepare_portrait_review(payload, [], sources)
    assert candidate is not None
    assert [item["text"] for item in candidate.evidence] == [first.text, second.text]
    receipt = await _receipt(monkeypatch, candidate, [_verdict(0, supported=False), _verdict(1)])
    selected = review.reviewed_portrait(payload, [], sources, receipt)
    assert receipt.approved_indices == (1,)
    assert [claim.text for claim in selected.portrait_claims] == [second.text]
    assert omitted.text not in grounded_portraits(selected.portrait_claims, [], sources.sections)[0]
    review.require_portrait_review(payload, [], sources, receipt)


async def test_removing_full_facets_cannot_promote_an_originally_omitted_brief_sentence(
    seven_facets,
    monkeypatch,
):
    output, sources, _ = seven_facets
    first, second = (output.portrait_claims[index] for index in (0, 2))
    monkeypatch.setattr(
        settings,
        "journal_portrait_brief_max_tokens",
        OpenAITokenCounter().count(first.text, "gpt-4o"),
    )
    payload = output.model_copy(update={"portrait_claims": [first, second]})
    candidate = review.prepare_portrait_review(payload, [], sources)
    assert candidate is not None
    assert [item["in_brief"] for item in candidate.evidence] == [True, False]
    receipt = await _receipt(monkeypatch, candidate, [_verdict(0, supported=False), _verdict(1)])
    selected = review.reviewed_portrait(payload, [], sources, receipt)
    assert [claim.in_brief for claim in selected.portrait_claims] == [False]
    assert grounded_portraits(selected.portrait_claims, [], sources.sections) == (second.text, None)


def test_complete_but_entirely_negative_review_remains_a_refusal(seven_facets):
    _, _, candidate = seven_facets
    with pytest.raises(ValueError, match="rejected"):
        review.approve_portrait_review(
            json.dumps({"reviews": [_verdict(index, supported=False) for index in range(7)]}),
            candidate,
        )


@pytest.mark.parametrize(
    "malformation",
    [
        "missing",
        "duplicate",
        "out_of_range",
        "bool_index",
        "numeric_bool",
        "string_bool",
        "trailing_json",
    ],
)
def test_incomplete_or_ambiguous_review_never_authorizes_a_subset(seven_facets, malformation):
    _, _, candidate = seven_facets
    verdicts = _mixed_verdicts()
    if malformation == "missing":
        verdicts.pop()
    elif malformation == "duplicate":
        verdicts[1]["index"] = 0
    elif malformation == "out_of_range":
        verdicts[1]["index"] = 7
    elif malformation == "bool_index":
        verdicts[1]["index"] = True
    elif malformation == "numeric_bool":
        verdicts[1]["supported"] = 1
    elif malformation == "string_bool":
        verdicts[1]["supported"] = "true"
    raw = json.dumps({"reviews": verdicts})
    if malformation == "trailing_json":
        raw += " trailing"
    with pytest.raises(ValueError):
        review.approve_portrait_review(raw, candidate)


@pytest.mark.parametrize(
    "mutation",
    [
        "words",
        "proof",
        "brief_promote",
        "brief_demote",
        "selection_drop",
        "selection_add",
        "reviewed_digest",
        "publication_digest",
    ],
)
async def test_receipt_cannot_bless_changed_selected_material_or_selection(
    seven_facets, monkeypatch, mutation
):
    output, sources, candidate = seven_facets
    receipt = await _receipt(monkeypatch, candidate, _mixed_verdicts())
    if mutation == "words":
        output.portrait_claims[0] = output.portrait_claims[0].model_copy(
            update={"text": "Il préfère désormais un traitement autonome de ses courriels."}
        )
    elif mutation == "proof":
        sources = PortraitSourceBundle(
            {"memories": sources.sections["memories"] + " An additional restriction applies."},
            sources.provenance,
        )
    elif mutation == "brief_promote":
        output.portrait_claims[1] = output.portrait_claims[1].model_copy(update={"in_brief": True})
    elif mutation == "brief_demote":
        output.portrait_claims[0] = output.portrait_claims[0].model_copy(update={"in_brief": False})
    elif mutation == "selection_drop":
        receipt = replace(receipt, approved_indices=(1, 2, 5))
    elif mutation == "selection_add":
        receipt = replace(receipt, approved_indices=(0, 1, 2, 3, 5))
    elif mutation == "reviewed_digest":
        receipt = replace(receipt, reviewed_digest="0" * 64)
    else:
        receipt = replace(receipt, digest="0" * 64)
    with pytest.raises(ValueError):
        review.require_portrait_review(output, [], sources, receipt)


async def test_journal_proof_revision_change_cannot_reuse_a_partial_review_receipt(monkeypatch):
    entry = SimpleNamespace(
        id=uuid4(),
        content="WHEN deleting sensitive mail -> DO ask for explicit confirmation.",
        revision=2,
        theme="learnings",
        level="L1",
        confidence="medium",
        evidence_count=0,
        contradiction_count=0,
    )
    sources = PortraitSourceBundle({}, {})
    first = PortraitClaim(
        facet="interaction",
        text="Une suppression de courriel sensible exige son accord préalable.",
        supports=[PortraitSupport(source=f"journal:{entry.id}", quote=entry.content)],
    )
    second = first.model_copy(
        update={"text": "Il souhaite maîtriser toutes les décisions qui le concernent."}
    )
    output = MaintenanceOutput(valid=True, portrait_claims=[first, second])
    candidate = review.prepare_portrait_review(output, [entry], sources)
    assert candidate is not None
    receipt = await _receipt(
        monkeypatch, candidate, [_verdict(0), _verdict(1, scope_preserved=False)]
    )
    review.require_portrait_review(output, [entry], sources, receipt)
    entry.revision = 3
    with pytest.raises(ValueError):
        review.require_portrait_review(output, [entry], sources, receipt)


def test_review_verdict_order_does_not_reorder_selected_paragraphs(seven_facets):
    _, _, candidate = seven_facets
    accepted = review.approve_portrait_review(
        json.dumps({"reviews": list(reversed(_mixed_verdicts()))}), candidate
    )
    assert accepted == (0, 1, 2, 5)


@pytest.mark.parametrize(
    "indices", [(), (0, 0, 1), (5, 2, 1, 0), (-1, 0, 1), (0, 1, 7), (False, 1, 2, 5)]
)
async def test_invalid_internal_receipt_indices_cannot_select_an_unreviewed_claim(
    seven_facets, monkeypatch, indices
):
    output, sources, candidate = seven_facets
    receipt = await _receipt(monkeypatch, candidate, _mixed_verdicts())
    with pytest.raises(ValueError):
        review.require_portrait_review(
            output, [], sources, replace(receipt, approved_indices=indices)
        )


async def test_selected_word_mutation_cannot_turn_reviewed_prose_into_unreviewed_empty_compilation(
    seven_facets,
    monkeypatch,
):
    output, sources, _ = seven_facets
    short = output.portrait_claims[1].model_copy(update={"in_brief": False})
    payload = output.model_copy(update={"portrait_claims": [short]})
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 40)
    candidate = review.prepare_portrait_review(payload, [], sources)
    assert candidate is not None
    receipt = await _receipt(monkeypatch, candidate, [_verdict(0)])
    # Still schema-valid natural prose, but now exceeds the unchanged full budget.
    large = PortraitClaim(
        facet=short.facet,
        text=short.text * 20,
        supports=short.supports,
        in_brief=False,
    )
    assert len(large.text) <= 2000
    payload.portrait_claims = [large]
    assert review.prepare_portrait_review(payload, [], sources) is None
    with pytest.raises(ValueError):
        review.require_portrait_review(payload, [], sources, receipt)


@pytest.mark.parametrize("missing_claims", [None, []])
async def test_existing_review_receipt_cannot_bless_disappearing_candidate(
    seven_facets, monkeypatch, missing_claims
):
    output, sources, candidate = seven_facets
    receipt = await _receipt(monkeypatch, candidate, _mixed_verdicts())
    output.portrait_claims = missing_claims
    with pytest.raises(ValueError):
        review.require_portrait_review(output, [], sources, receipt)


async def test_publication_consumer_stores_only_approved_words_and_canonical_private_supports(
    seven_facets,
    monkeypatch,
):
    output, sources, candidate = seven_facets
    receipt = await _receipt(monkeypatch, candidate, _mixed_verdicts())
    user = SimpleNamespace(id=uuid4())
    service = SimpleNamespace(get_all_active=AsyncMock(return_value=[]))
    snapshot = ConsolidationSnapshot(uuid4(), 0, 0, datetime.now(UTC), {})
    await _publish_portrait(user, service, output, sources, snapshot, 0, False, None, receipt, 0)
    expected = [output.portrait_claims[index] for index in (0, 1, 2, 5)]
    assert user.journal_portrait_full == "\n\n".join(claim.text for claim in expected)
    assert user.journal_portrait_brief == "\n\n".join(
        claim.text for claim in expected if claim.in_brief
    )
    stored = user.journal_portrait_sources
    assert [claim["text"] for claim in stored["claims"]] == [claim.text for claim in expected]
    assert stored["omitted_claims"] == 3
    assert stored["portrait_pending"] is False
    assert stored["portrait_review"]["approved_indices"] == [0, 1, 2, 5]
    assert all(
        claim["supports"] == [{"source": "memories", "quote": sources.sections["memories"]}]
        for claim in stored["claims"]
    )
    service.get_all_active.assert_awaited_once_with(user.id)

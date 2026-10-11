"""Semantic publication policy and accounted review attempts, without providers."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.core.config import settings
from src.domains.journals import portrait_review as review
from src.domains.journals.consolidation_output import (
    MaintenanceAction,
    MaintenanceOutput,
    PortraitClaim,
    PortraitSupport,
)
from src.domains.journals.models import JournalEntry
from src.domains.journals.portrait_sources import PortraitSourceBundle
from src.infrastructure.cache.pricing_cache import capture_pricing_snapshot
from src.infrastructure.llm.token_capture import TokenCaptureHandler

pytestmark = pytest.mark.unit


def _verdict(index: Any = 0, **changes: Any) -> dict[str, Any]:
    return {
        "index": index,
        "supported": True,
        "scope_preserved": True,
        "uncertainty_preserved": True,
        "synthesized": True,
        **changes,
    }


def _response(raw: str, tokens_in: int = 20, tokens_out: int = 3, **metadata: Any) -> AIMessage:
    return AIMessage(
        content=raw,
        usage_metadata={
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        },
        response_metadata=metadata,
    )


@pytest.fixture
def portrait_case(monkeypatch):
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 1000)
    monkeypatch.setattr(settings, "journal_portrait_brief_max_tokens", 1000)
    monkeypatch.setattr(review, "get_effective_context_window", lambda _: 128000)
    entry = JournalEntry(
        id=uuid4(),
        user_id=uuid4(),
        content="WHEN an urgent step is requested -> DO state one next action BECAUSE time is limited.",
        theme="self_reflection",
        level="L1",
        confidence="medium",
        revision=2,
        evidence_count=1,
        contradiction_count=0,
    )
    claim = PortraitClaim(
        facet="interaction",
        text="When he asks for urgent help, prioritize one next action that he can take immediately.",
        supports=[PortraitSupport(source=f"journal:{entry.id}", quote=entry.content)],
        in_brief=True,
    )
    return (
        MaintenanceOutput(portrait_claims=[claim], valid=True),
        [entry],
        PortraitSourceBundle({}, {}),
    )


@pytest.fixture
def candidate(portrait_case):
    prepared = review.prepare_portrait_review(*portrait_case)
    assert prepared is not None
    return prepared


@pytest.fixture
def synthetic_runtime(monkeypatch):
    """Real capture and claim semantics, with an in-memory synthetic tariff."""
    monkeypatch.setattr(
        "src.infrastructure.llm.token_capture.get_cached_cost_usd_eur",
        lambda **kw: ((kw["prompt_tokens"] + kw["completion_tokens"]) * 0.001,) * 2,
    )
    monkeypatch.setattr(
        "src.infrastructure.llm.token_capture.get_cached_usd_eur_rate", lambda _: 1.0
    )
    monkeypatch.setattr(review, "time", lambda: 1000.0)
    monkeypatch.setattr(review, "get_effective_context_window", lambda _: 128000)
    capture = TokenCaptureHandler()
    settlements = []

    async def persist(**kwargs):
        settlements.append((kwargs, capture.claim_billing_records(kwargs["model_name"])))

    return {
        "llm": object(),
        "user_id": uuid4(),
        "run_id": "synthetic-consolidation-run",
        "configured_model": "synthetic-configured-model",
        "requested_model": "synthetic-requested-model",
        "capture": capture,
        "persist": persist,
    }, settlements


def test_all_exact_verdicts_can_arrive_out_of_order(candidate):
    two_facets = replace(candidate, evidence=[candidate.evidence[0], {"index": 1}])
    review.approve_portrait_review(json.dumps({"reviews": [_verdict(1), _verdict(0)]}), two_facets)


@pytest.mark.parametrize("indices", [[0, 0], [0, 2], [0]])
def test_right_count_cannot_hide_a_duplicate_or_unknown_index(candidate, indices):
    two_facets = replace(candidate, evidence=[candidate.evidence[0], {"index": 1}])
    with pytest.raises(ValueError, match="Incomplete or duplicate"):
        review.approve_portrait_review(
            json.dumps({"reviews": [_verdict(index) for index in indices]}), two_facets
        )


@pytest.mark.parametrize(
    "criterion", ["supported", "scope_preserved", "uncertainty_preserved", "synthesized"]
)
def test_one_rejected_semantic_criterion_refuses_publication(candidate, criterion):
    with pytest.raises(ValueError, match="rejected"):
        review.approve_portrait_review(
            json.dumps({"reviews": [_verdict(**{criterion: False})]}), candidate
        )


@pytest.mark.parametrize(
    "criterion", ["supported", "scope_preserved", "uncertainty_preserved", "synthesized"]
)
@pytest.mark.parametrize("value", ["true", 1, None])
def test_semantic_verdicts_require_actual_booleans(candidate, criterion, value):
    with pytest.raises(ValueError, match="Invalid"):
        review.approve_portrait_review(
            json.dumps({"reviews": [_verdict(**{criterion: value})]}), candidate
        )


@pytest.mark.parametrize("index", [True, "0", 0.0, -1])
def test_indices_require_nonnegative_actual_integers(candidate, index):
    with pytest.raises(ValueError, match="Invalid"):
        review.approve_portrait_review(json.dumps({"reviews": [_verdict(index)]}), candidate)


@pytest.mark.parametrize("indices", [[], [1], [0, 0], [0, 1], [0, 2]])
def test_missing_duplicate_or_unknown_verdict_indices_refuse(candidate, indices):
    with pytest.raises(ValueError):
        review.approve_portrait_review(
            json.dumps({"reviews": [_verdict(index) for index in indices]}), candidate
        )


@pytest.mark.parametrize(
    "raw",
    [
        '{"reviews":[',
        '{"reviews":[]} trailing commentary',
        '```json\n{"reviews":[]}\n```',
        '{"reviews":[],"reviews":[]}',
        '{"reviews":[{"index":0,"index":1,"supported":true,"scope_preserved":true,"uncertainty_preserved":true,"synthesized":true}]}',
        json.dumps({"reviews": [_verdict(approved=True)]}),
        json.dumps({"reviews": [_verdict()], "self_approved": True}),
        json.dumps({"reviews": [{"index": 0, "supported": True}]}),
    ],
)
def test_review_payload_must_be_complete_unambiguous_and_only_its_contract(candidate, raw):
    with pytest.raises(ValueError, match="Invalid"):
        review.approve_portrait_review(raw, candidate)


def test_preparation_is_deterministic_and_records_complete_current_private_proofs(portrait_case):
    first = review.prepare_portrait_review(*portrait_case)
    second = review.prepare_portrait_review(*portrait_case)
    assert first == second
    assert first is not None and len(first.digest) == 64
    proof = first.evidence[0]["supports"][0]
    entry = portrait_case[1][0]
    assert proof == {
        "source": f"journal:{entry.id}",
        "quote": entry.content,
        "revision": 2,
        "theme": "self_reflection",
        "level": "L1",
        "confidence": "medium",
        "evidence_count": 1,
        "contradiction_count": 0,
    }
    assert first.evidence[0]["in_brief"] is True
    assert first.evidence[0]["provisional"] is False


def test_a_publication_requires_its_exact_review_receipt(portrait_case, candidate):
    with pytest.raises(ValueError, match="lacks"):
        review.require_portrait_review(*portrait_case, None)
    receipt = review.PortraitReviewReceipt(candidate.digest, "synthetic-model", 123.0)
    review.require_portrait_review(*portrait_case, receipt)
    assert receipt.provenance() == {
        "policy": review.JOURNAL_PORTRAIT_POLICY_VERSION,
        "digest": candidate.digest,
        "model": "synthetic-model",
        "reviewed_at": 123.0,
    }


@pytest.mark.parametrize("mutation", ["text", "revision", "proof", "brief", "confidence"])
def test_receipt_cannot_be_reused_after_candidate_or_proof_changes(
    portrait_case, candidate, mutation
):
    output, entries, sources = portrait_case
    claim, entry = output.portrait_claims[0], entries[0]
    if mutation == "text":
        claim.text = "For an urgent request, offer him one immediate next action."
    elif mutation == "revision":
        entry.revision += 1
    elif mutation == "proof":
        entry.content += " The condition applies only when explicitly requested."
        claim.supports[0].quote = entry.content
    elif mutation == "brief":
        claim.in_brief = False
    else:
        entry.confidence = "high"
    receipt = review.PortraitReviewReceipt(candidate.digest, "synthetic-model", 123.0)
    with pytest.raises(ValueError, match="lacks"):
        review.require_portrait_review(output, entries, sources, receipt)


def test_changed_source_cannot_be_saved_by_an_old_exact_quote(portrait_case, candidate):
    portrait_case[1][0].content = "A replacement rule after explicit correction."
    receipt = review.PortraitReviewReceipt(candidate.digest, "synthetic-model", 123.0)
    with pytest.raises(ValueError, match="complete current"):
        review.require_portrait_review(*portrait_case, receipt)


@pytest.mark.parametrize("operation", ["update", "delete", "merge_winner", "merge_loser"])
def test_support_changed_by_the_same_maintenance_cannot_be_published(portrait_case, operation):
    output, entries, _ = portrait_case
    identifier = str(entries[0].id)
    if operation == "update":
        action = MaintenanceAction(action="update", entry_id=identifier, title="Updated title")
    elif operation == "delete":
        action = MaintenanceAction(action="delete", entry_id=identifier)
    elif operation == "merge_winner":
        action = MaintenanceAction(action="merge", entry_id=identifier, merge_source_ids=[uuid4()])
    else:
        action = MaintenanceAction(
            action="merge", entry_id=str(uuid4()), merge_source_ids=[entries[0].id]
        )
    output.actions = [action]
    with pytest.raises(ValueError, match="survive maintenance unchanged"):
        review.prepare_portrait_review(*portrait_case)


def test_unrelated_maintenance_does_not_invalidate_proofs(portrait_case):
    portrait_case[0].actions = [MaintenanceAction(action="delete", entry_id=str(uuid4()))]
    assert review.prepare_portrait_review(*portrait_case) is not None


@pytest.mark.parametrize("empty", [None, []])
def test_no_candidate_needs_no_semantic_receipt(portrait_case, empty):
    portrait_case[0].portrait_claims = empty
    assert review.prepare_portrait_review(*portrait_case) is None
    review.require_portrait_review(*portrait_case, None)


def test_whole_facet_omitted_by_budget_needs_no_review(portrait_case, monkeypatch):
    monkeypatch.setattr(settings, "journal_portrait_full_max_tokens", 1)
    assert review.prepare_portrait_review(*portrait_case) is None
    review.require_portrait_review(*portrait_case, None)


def test_brief_budget_decision_is_bound_in_the_receipt(portrait_case, candidate, monkeypatch):
    monkeypatch.setattr(settings, "journal_portrait_brief_max_tokens", 1)
    prepared = review.prepare_portrait_review(*portrait_case)
    assert prepared is not None and prepared.evidence[0]["in_brief"] is False
    assert prepared.digest != candidate.digest


def test_actual_shared_proof_registry_deduplicates_only_equal_complete_metadata(candidate):
    proof = candidate.evidence[0]["supports"][0]
    reordered = dict(reversed(list(proof.items())))
    updated = {**proof, "revision": proof["revision"] + 1}
    facets = [
        candidate.evidence[0],
        {**candidate.evidence[0], "index": 1, "supports": [reordered, updated]},
    ]
    compact = review.compact_review_evidence(facets)
    assert compact["proofs"] == [proof, updated]
    assert [facet["support_indices"] for facet in compact["facets"]] == [[0], [0, 1]]
    assert all("supports" not in facet for facet in compact["facets"])
    assert facets[0]["supports"] == [proof]  # Request compaction does not mutate the receipt input.
    wire = review.portrait_review_messages(facets, "synthetic-configured-model")
    assert json.loads(wire[1].content) == compact
    assert (
        wire[1].content.count(proof["quote"]) == 2
    )  # Equal quotes at different revisions stay distinct.


@pytest.mark.parametrize("boundary", [0, 1])
def test_entire_system_and_json_request_reserves_framing_under_model_limit(
    candidate, monkeypatch, boundary
):
    monkeypatch.setattr(review, "get_effective_context_window", lambda _: 200)
    counter = MagicMock()
    counter.count.return_value = 100 - 32 + boundary
    monkeypatch.setattr(review, "OpenAITokenCounter", lambda: counter)
    if boundary:
        with pytest.raises(ValueError, match="complete-request budget"):
            review.portrait_review_messages(candidate.evidence, "synthetic-configured-model")
    else:
        messages = review.portrait_review_messages(candidate.evidence, "synthetic-configured-model")
        assert len(messages) == 2
    rendered, model = counter.count.call_args.args
    assert "independently review" in rendered
    assert candidate.evidence[0]["text"] in rendered
    assert candidate.evidence[0]["supports"][0]["quote"] in rendered
    assert '"proofs"' in rendered and '"support_indices"' in rendered
    assert model == "synthetic-configured-model"


@pytest.mark.asyncio
async def test_schema_accepted_proof_amplification_is_refused_before_invoke_or_billing(
    portrait_case, synthetic_runtime
):
    _, _, sources = portrait_case
    quotes = ["- " + " 1," * 1660 + f" {index}" for index in range(8)]
    sources.sections["memories"] = "\n".join(quotes)
    claims = [
        PortraitClaim(
            facet="interaction",
            text=f"For an urgent request, support a next action he can carry out with nuance {index}.",
            supports=[PortraitSupport(source="memories", quote=quote) for quote in quotes],
            in_brief=False,
        )
        for index in range(32)
    ]
    output = MaintenanceOutput(portrait_claims=claims, valid=True)
    prepared = review.prepare_portrait_review(output, [], sources)
    assert prepared is not None and len(prepared.evidence) == 32
    compact = review.compact_review_evidence(prepared.evidence)
    assert (
        len(compact["proofs"]) == 8
    )  # 256 schema-valid references reduce to eight complete proofs.
    runtime, settlements = synthetic_runtime
    invoke = AsyncMock()
    with pytest.raises(ValueError, match="complete-request budget"):
        await review.review_portrait(prepared, invoke=invoke, **runtime)
    invoke.assert_not_awaited()
    assert settlements == []
    assert runtime["capture"].get_billing_records(runtime["configured_model"]) == ()


@pytest.mark.asyncio
async def test_review_reuses_configured_operation_and_persists_its_actual_response(
    candidate, synthetic_runtime
):
    runtime, settlements = synthetic_runtime
    result = _response(json.dumps({"reviews": [_verdict()]}), model_name="synthetic-actual-model")
    invoke = AsyncMock(return_value=result)
    receipt = await review.review_portrait(candidate, invoke=invoke, **runtime)
    assert receipt.digest == candidate.digest and receipt.model == "synthetic-actual-model"
    assert receipt.reviewed_at == 1000.0
    invoke.assert_awaited_once()
    call = invoke.await_args.kwargs
    assert call["llm"] is runtime["llm"]
    assert call["llm_type"] == "journal_consolidation"
    assert call["user_id"] == str(runtime["user_id"])
    assert call["config"]["callbacks"] == [runtime["capture"]]
    assert isinstance(call["messages"][0], SystemMessage)
    assert isinstance(call["messages"][1], HumanMessage)
    wire = json.loads(call["messages"][1].content)
    assert wire["proofs"] == candidate.evidence[0]["supports"]
    assert wire["facets"][0]["support_indices"] == [0]
    assert wire["facets"][0]["text"] == candidate.evidence[0]["text"]
    assert "supports" not in wire["facets"][0]
    persisted, records = settlements[0]
    assert persisted["result"] is result and persisted["failed"] is False
    assert persisted["parent_run_id"] == runtime["run_id"]
    assert persisted["requested_model"] == runtime["requested_model"]
    assert persisted["user_id"] == str(runtime["user_id"])
    assert persisted["conversation_id"] is None and persisted["session_id"] == "consolidation"
    assert len(records) == 1 and records[0].model_name == "synthetic-actual-model"
    assert records[0].cost_eur == pytest.approx(0.023)
    assert runtime["capture"].claim_billing_records(runtime["configured_model"]) == ()


def _seed_accounted_draft(runtime):
    capture = runtime["capture"]
    capture.ensure_response_record(
        _response("synthetic draft", 10, 2),
        model_name=runtime["configured_model"],
        started_at=999.0,
        snapshot=capture_pricing_snapshot(),
    )
    records = capture.claim_billing_records(runtime["configured_model"])
    assert len(records) == 1 and records[0].cost_eur == pytest.approx(0.012)


@pytest.mark.asyncio
@pytest.mark.parametrize("callbacks", [False, True])
async def test_second_paid_phase_is_recorded_once_with_fallback_or_callbacks(
    candidate, synthetic_runtime, callbacks
):
    runtime, settlements = synthetic_runtime
    _seed_accounted_draft(runtime)
    result = _response(json.dumps({"reviews": [_verdict()]}))

    async def invoke(**kwargs):
        if callbacks:
            capture = kwargs["config"]["callbacks"][0]
            callback_run = uuid4()
            capture.on_llm_start(
                {"kwargs": {"model": runtime["configured_model"]}}, [], run_id=callback_run
            )
            capture.on_llm_end(
                LLMResult(generations=[[ChatGeneration(message=result)]]), run_id=callback_run
            )
        return result

    await review.review_portrait(candidate, invoke=invoke, **runtime)
    assert len(settlements) == 1 and len(settlements[0][1]) == 1
    assert settlements[0][1][0].tokens_in == 20
    records = runtime["capture"].get_billing_records(runtime["configured_model"])
    assert len(records) == 2
    assert sum(record.tokens_in for record in records) == 30
    assert sum(record.tokens_out for record in records) == 5
    assert sum(record.cost_eur for record in records) == pytest.approx(0.035)


@pytest.mark.asyncio
@pytest.mark.parametrize("partial_usage", [False, True])
async def test_review_provider_failure_settles_only_known_new_spend_before_raising(
    candidate, synthetic_runtime, partial_usage
):
    runtime, settlements = synthetic_runtime
    _seed_accounted_draft(runtime)
    failure = RuntimeError("synthetic provider failure")

    async def invoke(**kwargs):
        if partial_usage:
            capture = kwargs["config"]["callbacks"][0]
            callback_run = uuid4()
            capture.on_llm_start(
                {"kwargs": {"model": runtime["configured_model"]}}, [], run_id=callback_run
            )
            partial = LLMResult(generations=[[ChatGeneration(message=_response("partial", 3, 1))]])
            capture.on_llm_error(failure, run_id=callback_run, response=partial)
        raise failure

    with pytest.raises(RuntimeError, match="synthetic provider failure"):
        await review.review_portrait(candidate, invoke=invoke, **runtime)
    persisted, records = settlements[0]
    assert persisted["result"] is None and persisted["failed"] is True
    assert persisted["parent_run_id"] == runtime["run_id"]
    assert len(records) == int(partial_usage)
    all_records = runtime["capture"].get_billing_records(runtime["configured_model"])
    assert sum(record.cost_eur for record in all_records) == pytest.approx(
        0.016 if partial_usage else 0.012
    )
    if partial_usage:
        assert records[0].status == "error" and records[0].failure_kind == "unknown"
    assert runtime["capture"].claim_billing_records(runtime["configured_model"]) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["malformed", "semantic_rejection", "truncated"])
async def test_unusable_paid_review_is_settled_but_cannot_create_a_receipt(
    candidate, synthetic_runtime, failure
):
    runtime, settlements = synthetic_runtime
    raw = (
        '{"reviews":['
        if failure == "malformed"
        else json.dumps({"reviews": [_verdict(supported=failure != "semantic_rejection")]})
    )
    metadata = {"finish_reason": "length"} if failure == "truncated" else {}
    result = _response(raw, **metadata)
    invoke = AsyncMock(return_value=result)
    with pytest.raises(ValueError):
        await review.review_portrait(candidate, invoke=invoke, **runtime)
    invoke.assert_awaited_once()
    persisted, records = settlements[0]
    assert persisted["result"] is result
    assert persisted["failed"] is False  # Provider success remains billed despite unusable meaning.
    assert len(records) == 1 and records[0].cost_eur == pytest.approx(0.023)

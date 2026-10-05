"""Read-only qualifications never turn uncertainty or omissions into disappearing data."""

import asyncio
import importlib
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.llm_config.jev_settings import JevSnapshot
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("ready_snapshot")]


@pytest.fixture
def ready_snapshot():
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    snapshot = JevSnapshot(True, "ready", MagicMock())
    with patch.object(module, "load_jev_snapshot", AsyncMock(return_value=snapshot)) as load:
        yield load


async def test_debug_reports_the_applied_verdict_not_the_untrusted_provider_choice() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    attempt = DecisionAttempt(outcome="success", answers={"q0": answer("non_match", 0.7)})
    with (
        patch.object(module, "choose_many_with_jev", AsyncMock(return_value=attempt)),
        patch.object(module, "record_action", AsyncMock()) as record,
    ):
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="turn", query="Emails", items=[item(0)]
        )
    assert result is not None and result.items[0].verdict == "unknown"
    assert record.call_args.kwargs["action"] == "preview"
    assert record.call_args.kwargs["outcome"] == "uncertain"
    assert record.call_args.kwargs["applied_decisions"] == {"q0": "unknown"}
    assert record.call_args.kwargs["decision_labels"] == {"q0": "Update 0"}


def item(index: int, kind: RegistryItemType = RegistryItemType.EMAIL) -> RegistryItem:
    return RegistryItem(
        id=f"item_{index}",
        type=kind,
        payload={
            "subject": f"Update {index}",
            "body": "Please reply with the signed agreement.",
            "isRead": False,
        },
        meta=RegistryItemMeta(source="test", domain="email"),
    )


def answer(choice: str, confidence: float = 0.99) -> ChoiceAnswer:
    return ChoiceAnswer(
        type="choice",
        choice=choice,
        confidence=confidence,
        probabilities={
            key: 0.998 if key == choice else 0.001 for key in ("match", "non_match", "unknown")
        },
    )


async def test_matches_non_matches_and_unknowns_all_remain_inspectable() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    objects = [item(i) for i in range(4)]
    original = [value.model_dump() for value in objects]
    fake = AsyncMock(
        return_value=DecisionAttempt(
            outcome="success",
            answers={
                "q0": answer("match"),
                "q1": answer("non_match"),
                "q2": answer("unknown"),
                "q3": answer("non_match", 0.8),
            },
        )
    )
    with patch.object(module, "choose_many_with_jev", fake):
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="turn", query="Emails requiring a reply", items=objects
        )
    assert result is not None
    assert [(value.id, value.verdict) for value in result.items] == [
        ("item_0", "match"),
        ("item_1", "non_match"),
        ("item_2", "unknown"),
        ("item_3", "unknown"),
    ]
    assert [value.model_dump() for value in objects] == original
    assert result.items[0].excerpt == objects[0].payload["body"]
    request = fake.call_args.kwargs
    assert request["state"]["query"] == "Emails requiring a reply"
    assert "signed agreement" in request["state"]["items"]["q0"]["body"]
    assert request["state"]["items"]["q0"]["isRead"] is False
    assert "q0" in request["questions"]["q0"].instructions


@pytest.mark.parametrize("outcome", ["disabled", "timeout", "invalid_response", "unavailable"])
async def test_unavailable_qualification_preserves_the_existing_path(outcome: str) -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    with patch.object(
        module, "choose_many_with_jev", AsyncMock(return_value=DecisionAttempt(outcome=outcome))
    ):
        assert (
            await module.qualify_collection(
                user_id=uuid4(), run_id="turn", query="Emails", items=[item(1)]
            )
            is None
        )


async def test_multiple_batches_cover_rows_after_first_24_with_original_keys() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    objects = [item(i) for i in range(30)]

    async def classify(**kwargs):
        return DecisionAttempt(
            outcome="success", answers={key: answer("match") for key in kwargs["questions"]}
        )

    with patch.object(module, "choose_many_with_jev", AsyncMock(side_effect=classify)) as fake:
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="turn", query="Emails", items=objects
        )
    assert result is not None
    assert len(result.items) == 30
    assert result.evaluated_count == 30
    assert result.candidate_count == 30
    assert all(value.verdict == "match" for value in result.items)
    assert fake.await_count == 2
    assert set(fake.call_args_list[1].kwargs["questions"]) == {f"q{i}" for i in range(24, 30)}


@pytest.mark.parametrize(
    "kind", [RegistryItemType.DRAFT, RegistryItemType.SKILL_APP, RegistryItemType.MCP_APP]
)
async def test_interactive_or_mutating_items_are_never_qualified(kind: RegistryItemType) -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    with patch.object(module, "choose_many_with_jev", AsyncMock()) as fake:
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="turn", query="Anything", items=[item(1, kind)]
        )
    assert result is None
    fake.assert_not_awaited()


async def test_partial_or_foreign_answer_set_is_never_applied() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    with patch.object(
        module,
        "choose_many_with_jev",
        AsyncMock(
            return_value=DecisionAttempt(
                outcome="success",
                answers={"foreign": answer("match")},
            )
        ),
    ):
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="turn", query="Emails", items=[item(1)]
        )
    assert result is None


async def test_incomplete_evidence_is_not_sent_or_promoted_to_a_confident_verdict() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    objects = [item(0), item(1)]
    objects[0].payload["body"] = "x" * 40_000
    with patch.object(
        module,
        "choose_many_with_jev",
        AsyncMock(
            return_value=DecisionAttempt(
                outcome="success",
                answers={"q1": answer("match")},
            )
        ),
    ) as fake:
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="turn", query="Emails", items=objects
        )
    assert result is not None
    assert [value.verdict for value in result.items] == ["unknown", "match"]
    assert result.evaluated_count == 1
    assert set(fake.call_args.kwargs["questions"]) == {"q1"}


async def test_request_budget_accounts_for_instructions_and_multibyte_evidence() -> None:
    import json

    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    objects = [item(i) for i in range(100)]
    for obj in objects:
        obj.payload["body"] = "界" * 600
    with patch.object(
        module, "choose_many_with_jev", AsyncMock(return_value=DecisionAttempt(outcome="timeout"))
    ) as fake:
        await module.qualify_collection(
            user_id=uuid4(), run_id="turn", query="Emails", items=objects
        )
    request = fake.call_args.kwargs
    body = json.dumps(
        {
            "model": "m" * 100,
            "state": request["state"],
            "questions": {key: value.model_dump() for key, value in request["questions"].items()},
        },
        ensure_ascii=False,
    ).encode()
    assert len(body) <= 32_000
    assert 1 <= len(request["questions"]) < 24


async def test_missing_mail_status_remains_unknown_without_a_fabricated_flag() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    candidate = item(0)
    candidate.payload.pop("isRead")
    with patch.object(
        module,
        "choose_many_with_jev",
        AsyncMock(
            return_value=DecisionAttempt(outcome="success", answers={"q0": answer("unknown")})
        ),
    ) as native:
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="turn", query="Unread emails", items=[candidate]
        )
    assert result is not None and result.items[0].verdict == "unknown"
    assert "isRead" not in native.call_args.kwargs["state"]["items"]["q0"]
    assert "labelIds" not in native.call_args.kwargs["state"]["items"]["q0"]


async def test_complete_75_item_coverage_is_logged_without_private_data() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    objects = [item(i, RegistryItemType.EVENT) for i in range(75)]
    objects[70].payload["subject"] = "Podiatrist appointment"
    original = [value.model_dump() for value in objects]

    async def qualify(**kwargs):
        return DecisionAttempt(
            outcome="success",
            answers={key: answer("non_match", 0.88) for key in kwargs["questions"]},
        )

    with (
        patch.object(module, "choose_many_with_jev", AsyncMock(side_effect=qualify)),
        patch.object(module.logger, "info") as logged,
    ):
        result = await module.qualify_collection(
            user_id=uuid4(),
            run_id="synthetic",
            query="Upcoming medical appointments",
            items=objects,
        )
    assert result is not None
    assert result.candidate_count == 75 and result.evaluated_count == 75
    assert len(result.items) == 75 and all(value.verdict == "unknown" for value in result.items)
    assert result.items[70].id == objects[70].id
    assert [value.model_dump() for value in objects] == original
    counts = logged.call_args.kwargs
    assert counts["candidate_count"] == 75
    assert counts["evaluated_count"] == 75
    assert counts["unevaluated_count"] == 0
    assert counts["omitted_count"] == 0
    assert "Upcoming" not in str(counts) and "Podiatrist" not in str(counts)


async def test_every_batch_reuses_one_configuration_and_failed_batch_keeps_other_verdicts(
    ready_snapshot,
) -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")

    async def classify(**kwargs):
        if "q24" in kwargs["questions"]:
            return DecisionAttempt(outcome="invalid_response")
        return DecisionAttempt(
            outcome="success", answers={key: answer("match") for key in kwargs["questions"]}
        )

    with (
        patch.object(module, "choose_many_with_jev", AsyncMock(side_effect=classify)) as native,
        patch.object(module, "record_action", AsyncMock()) as recorded,
    ):
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="r", query="Emails", items=[item(i) for i in range(30)]
        )
    assert result is not None
    assert [entry.verdict for entry in result.items] == ["match"] * 24 + ["unknown"] * 6
    assert ready_snapshot.await_count == 1
    assert all(
        call.kwargs["snapshot"] is ready_snapshot.return_value for call in native.call_args_list
    )
    coverages = [call.kwargs["collection_coverage"] for call in recorded.call_args_list]
    assert [coverage.batch_index for coverage in coverages] == [1, 2]
    assert all(
        coverage.evaluated_count == 30 and coverage.unknown_count == 6 for coverage in coverages
    )
    assert recorded.call_args_list[1].kwargs["action"] == "fallback"


async def test_cancellation_joins_active_batches_and_never_starts_queued_batches() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    entered = asyncio.Event()
    active = 0
    stopped = 0

    async def blocked(**kwargs):
        nonlocal active, stopped
        active += 1
        if active == 2:
            entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped += 1
            active -= 1

    with patch.object(module, "choose_many_with_jev", AsyncMock(side_effect=blocked)) as native:
        work = asyncio.create_task(
            module.qualify_collection(
                user_id=uuid4(), run_id="r", query="Emails", items=[item(i) for i in range(100)]
            )
        )
        await asyncio.wait_for(entered.wait(), 0.5)
        work.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(work, 0.5)
    assert native.await_count == stopped == 2 and active == 0


async def test_lot_cap_and_oversized_records_remain_explicitly_unknown() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    objects = [item(i) for i in range(110)]
    # Whole records near the request limit fit only one item per batch.
    for candidate in objects:
        candidate.payload.update({f"part_{i}": "界" * 1000 for i in range(8)})

    async def classify(**kwargs):
        return DecisionAttempt(
            outcome="success", answers={key: answer("match") for key in kwargs["questions"]}
        )

    with (
        patch.object(module, "choose_many_with_jev", AsyncMock(side_effect=classify)) as native,
        patch.object(module, "record_action", AsyncMock()) as recorded,
    ):
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="r", query="Emails", items=objects
        )
    assert result is not None and native.await_count == module.MAX_BATCHES
    assert result.evaluated_count == 8 and result.omitted_count == 10
    assert len(result.items) == 100 and all(row.verdict == "unknown" for row in result.items[8:])
    coverage = recorded.call_args.kwargs["collection_coverage"]
    assert coverage.candidate_count == 110 and coverage.unevaluated_count == 102
    assert coverage.unknown_count == 0 and coverage.omitted_count == 10


async def test_local_runtime_exception_is_not_counted_as_a_submitted_candidate() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")

    async def classify(**kwargs):
        if "q24" in kwargs["questions"]:
            raise RuntimeError("quota guard")
        return DecisionAttempt(
            outcome="success", answers={key: answer("match") for key in kwargs["questions"]}
        )

    with (
        patch.object(module, "choose_many_with_jev", AsyncMock(side_effect=classify)),
        patch.object(module, "record_action", AsyncMock()) as recorded,
    ):
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="r", query="Emails", items=[item(i) for i in range(30)]
        )
    assert result is not None and result.evaluated_count == 24
    coverage = recorded.call_args.kwargs["collection_coverage"]
    assert coverage.unevaluated_count == 6 and coverage.unknown_count == 0
    assert [row.verdict for row in result.items[24:]] == ["unknown"] * 6


@pytest.mark.parametrize("outcome", ["invalid_request", "invalid_questions", "request_too_large"])
async def test_local_preflight_result_is_not_counted_as_submitted(outcome) -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")

    async def classify(**kwargs):
        if "q24" in kwargs["questions"]:
            return DecisionAttempt(outcome=outcome)
        return DecisionAttempt(
            outcome="success", answers={key: answer("match") for key in kwargs["questions"]}
        )

    with (
        patch.object(module, "choose_many_with_jev", AsyncMock(side_effect=classify)),
        patch.object(module, "record_action", AsyncMock()) as recorded,
    ):
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="r", query="Emails", items=[item(i) for i in range(30)]
        )
    assert result is not None and result.evaluated_count == 24
    assert recorded.call_args.kwargs["collection_coverage"].unevaluated_count == 6


async def test_calendar_application_facts_share_reference_and_cannot_be_spoofed_by_payload() -> (
    None
):
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    objects = [item(i, RegistryItemType.EVENT) for i in range(30)]
    for candidate in objects:
        candidate.payload.update(
            start={"dateTime": "2026-10-05T13:00:00+02:00"},
            application_facts={"start_at_or_after_reference": False},
        )
    reference = datetime(2026, 10, 4, 12, tzinfo=UTC)

    async def classify(**kwargs):
        return DecisionAttempt(
            outcome="success", answers={key: answer("unknown") for key in kwargs["questions"]}
        )

    with patch.object(module, "choose_many_with_jev", AsyncMock(side_effect=classify)) as native:
        await module.qualify_collection(
            user_id=uuid4(),
            run_id="r",
            query="Upcoming appointments",
            items=objects,
            reference_datetime=reference,
            timezone="Europe/Paris",
        )
    submitted = [call.kwargs["state"] for call in native.call_args_list]
    for state in submitted:
        assert set(state["application_facts"]) == set(state["items"])
        for key, facts in state["application_facts"].items():
            assert facts["reference_datetime"] == reference.isoformat()
            assert facts["start_at_or_after_reference"] is True
            assert state["items"][key]["application_facts"]["start_at_or_after_reference"] is False


async def test_incomplete_only_collection_records_zero_api_coverage_with_closed_reasons() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    candidate = item(0)
    candidate.payload["body"] = "private body " * 10_000
    with (
        patch.object(module, "choose_many_with_jev", AsyncMock()) as native,
        patch.object(module, "begin_trace", AsyncMock(return_value=None)) as begun,
        patch.object(module, "finish_trace", AsyncMock(return_value=None)) as finished,
        patch.object(module, "record_action", AsyncMock()) as recorded,
        patch.object(module.logger, "info") as logged,
    ):
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="r", query="Emails", items=[candidate]
        )
    assert result is None
    native.assert_not_awaited()
    assert begun.call_args.kwargs["state"] == {
        "candidate_count": 1,
        "omission_reasons": {
            "incomplete_evidence": 1,
            "empty_evidence": 0,
            "oversized_evidence": 0,
        },
    }
    assert begun.call_args.kwargs["question"] == {}
    assert finished.call_args.kwargs["counters"] is None
    assert finished.call_args.kwargs["reported_model"] is None
    coverage = recorded.call_args.kwargs["collection_coverage"]
    assert coverage.evaluated_count == coverage.unknown_count == 0
    assert coverage.unevaluated_count == 1 and coverage.batch_count is None
    assert logged.call_args.kwargs["outcome"] == "no_eligible_evidence"
    assert "private body" not in str(begun.call_args) + str(logged.call_args)


async def test_mutation_during_native_call_cannot_relabel_or_replace_judged_source() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    candidate = item(0)
    candidate.payload.update(subject="Initial acceptance", body="I accept the proposal.")

    async def classify(**kwargs):
        assert kwargs["state"]["items"]["q0"]["body"] == "I accept the proposal."
        candidate.payload.update(subject="Later rejection", body="I reject the proposal.")
        return DecisionAttempt(outcome="success", answers={"q0": answer("match")})

    with (
        patch.object(module, "choose_many_with_jev", AsyncMock(side_effect=classify)),
        patch.object(module, "record_action", AsyncMock()) as recorded,
    ):
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="r", query="Emails accepting the proposal", items=[candidate]
        )
    assert result is not None
    assert result.items[0].verdict == "match"
    assert result.items[0].title == "Initial acceptance"
    assert result.items[0].excerpt == "I accept the proposal."
    assert recorded.call_args.kwargs["decision_labels"] == {"q0": "Initial acceptance"}
    assert candidate.payload["body"] == "I reject the proposal."


async def test_unsupported_json_snapshot_is_explicitly_omitted_without_stringification() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    candidate = item(0)
    candidate.payload["unsupported"] = object()
    with (
        patch.object(module, "choose_many_with_jev", AsyncMock()) as native,
        patch.object(module, "begin_trace", AsyncMock(return_value=None)) as begun,
        patch.object(module, "finish_trace", AsyncMock(return_value=None)),
        patch.object(module, "record_action", AsyncMock()),
    ):
        assert (
            await module.qualify_collection(
                user_id=uuid4(), run_id="r", query="Emails", items=[candidate]
            )
            is None
        )
    native.assert_not_awaited()
    assert begun.call_args.kwargs["state"]["omission_reasons"]["incomplete_evidence"] == 1


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"count": 10**5000},
        {"body": chr(0xD800)},
        {"subject": chr(0xDFFF)},
        {chr(0xD800): "Invalid key"},
        {"unsupported": object()},
        {"measure": float("nan")},
        {"measure": Decimal("NaN")},
        {"measure": Decimal("Infinity")},
        {"measurements": {1: "NUMERIC", "1": "TEXT"}},
    ],
    ids=[
        "large-integer",
        "surrogate-body",
        "surrogate-title",
        "surrogate-key",
        "non-json",
        "nan",
        "decimal-nan",
        "decimal-infinity",
        "nested-key-collision",
    ],
)
async def test_bad_candidate_does_not_prevent_valid_submission_or_change_known_charge(
    invalid_fields,
) -> None:
    from src.infrastructure.llm.decision_types import DecisionCharge

    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    bad, good = item(0), item(1)
    bad.payload.update(invalid_fields)
    charge = DecisionCharge(
        model="synthetic-native", input_tokens=123, output_tokens=0, cost_usd=0.001, cost_eur=0.0009
    )
    attempt = DecisionAttempt(outcome="success", answers={"q1": answer("match")}, charge=charge)
    with (
        patch.object(module, "choose_many_with_jev", AsyncMock(return_value=attempt)) as native,
        patch.object(module, "record_action", AsyncMock()) as recorded,
    ):
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="synthetic", query="Emails", items=[bad, good]
        )
    assert result is not None
    assert [entry.verdict for entry in result.items] == ["unknown", "match"]
    assert native.await_count == 1
    assert set(native.call_args.kwargs["questions"]) == {"q1"}
    assert set(native.call_args.kwargs["state"]["items"]) == {"q1"}
    coverage = recorded.call_args.kwargs["collection_coverage"]
    assert coverage.candidate_count == 2 and coverage.evaluated_count == 1
    assert coverage.unevaluated_count == 1 and coverage.unknown_count == 0
    assert attempt.charge is charge and charge.input_tokens == 123 and charge.cost_usd == 0.001
    for key, value in invalid_fields.items():
        assert bad.payload[key] is value
    import json

    json.dumps(result.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
    json.dumps(recorded.call_args.kwargs["decision_labels"], ensure_ascii=False).encode("utf-8")


async def test_all_bad_candidates_emit_zero_api_diagnostic_and_explicit_coverage() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    invalid_fields = [
        {"count": 10**5000},
        {"body": chr(0xD800)},
        {"subject": chr(0xDFFF)},
        {chr(0xD800): "Invalid key"},
        {"unsupported": object()},
        {"measure": float("nan")},
        {"measure": Decimal("NaN")},
        {"measure": Decimal("Infinity")},
        {"measurements": {1: "NUMERIC", "1": "TEXT"}},
    ]
    candidates = [item(index) for index in range(len(invalid_fields))]
    for candidate, fields in zip(candidates, invalid_fields, strict=True):
        candidate.payload.update(fields)
    with (
        patch.object(module, "choose_many_with_jev", AsyncMock()) as native,
        patch.object(module, "begin_trace", AsyncMock(return_value=None)) as begun,
        patch.object(module, "finish_trace", AsyncMock(return_value=None)) as finished,
        patch.object(module, "record_action", AsyncMock()) as recorded,
    ):
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="synthetic", query="Emails", items=candidates
        )
    assert result is None
    native.assert_not_awaited()
    assert begun.call_args.kwargs["state"]["omission_reasons"] == {
        "incomplete_evidence": len(candidates),
        "empty_evidence": 0,
        "oversized_evidence": 0,
    }
    assert finished.call_args.kwargs["outcome"] == "no_eligible_evidence"
    assert finished.call_args.kwargs["counters"] is None
    assert finished.call_args.kwargs["cost_eur"] is None
    coverage = recorded.call_args.kwargs["collection_coverage"]
    assert coverage.candidate_count == coverage.unevaluated_count == len(candidates)
    assert coverage.evaluated_count == coverage.unknown_count == 0

"""Read-only qualifications never turn uncertainty or omissions into disappearing data."""

import importlib
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer

pytestmark = pytest.mark.unit


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
    assert "signed agreement" in request["state"]["items"]["q0"]
    assert "False" in request["state"]["items"]["q0"]
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


async def test_oversized_collection_keeps_unexamined_rows_unknown_and_states_scope() -> None:
    module = importlib.import_module("src.domains.agents.display.jev_qualification")
    objects = [item(i) for i in range(30)]
    with patch.object(
        module,
        "choose_many_with_jev",
        AsyncMock(
            return_value=DecisionAttempt(
                outcome="success",
                answers={f"q{i}": answer("match") for i in range(24)},
            )
        ),
    ) as fake:
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="turn", query="Emails", items=objects
        )
    assert result is not None
    assert len(result.items) == 30
    assert result.evaluated_count == 24
    assert result.candidate_count == 30
    assert all(value.verdict == "unknown" for value in result.items[24:])
    assert len(fake.call_args.kwargs["questions"]) == 24


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

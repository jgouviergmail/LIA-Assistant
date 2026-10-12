"""JEV says what a guarded value IS; the code decides whether the parameter accepts it.

ADR-325 usage ``parameter_kind`` (ADR-120 amendment 2026-10-11). The judgment
only ADDS refusals the deterministic guard cannot see; every uncertain, failed
or switched-off path leaves the call to that guard.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.constants import JEV_PARAMETER_KIND_MAX_VALUES, JEV_PARAMETER_KIND_MIN_CONFIDENCE
from src.core.context import current_tracker
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.registry.catalogue import (
    CostProfile,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.semantic import jev_value_kind as module
from src.domains.agents.semantic.param_guard import GUARDED_SEMANTIC_TYPES
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer

pytestmark = pytest.mark.unit

OWNER = uuid4()
TRACKER = SimpleNamespace(user_id=OWNER, run_id="run-1")


def _manifest(params: list[tuple[str, str, str]]) -> ToolManifest:
    return ToolManifest(
        name="get_route_tool",
        agent="route_agent",
        description="fixture",
        parameters=[
            ParameterSchema(
                name=name,
                type=kind,
                description=f"{name} value",
                semantic_type=stype,
                required=False,
            )
            for name, kind, stype in params
        ],
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(),
        mutation_policy="read",
    )


ROUTE = _manifest([("destination", "string", "physical_address")])


def _answer(kind: str, confidence: float = 0.99) -> DecisionAttempt:
    return DecisionAttempt(
        outcome="success",
        answer=ChoiceAnswer(
            type="choice",
            choice=kind,
            confidence=confidence,
            probabilities=(
                {kind: 0.99, "other": 0.01} if kind != "other" else {"other": 0.99, "place": 0.01}
            ),
        ),
    )


async def _judge(
    args: dict[str, object],
    attempts: list[DecisionAttempt] | BaseException,
    *,
    manifest: ToolManifest = ROUTE,
    requested: bool = True,
    request: str | None = "Itinéraire vers chez Marc",
    tracker: object = TRACKER,
    proven: bool = False,
) -> tuple[object, AsyncMock]:
    native = AsyncMock(
        side_effect=attempts if isinstance(attempts, BaseException) else list(attempts)
    )
    snapshot = SimpleNamespace(requested=requested, readiness="ready", configuration=object())
    token = current_tracker.set(tracker)  # type: ignore[arg-type]
    try:
        with (
            patch.object(module, "available_manifest", return_value=manifest),
            patch.object(module, "proven_by_binding", return_value=proven),
            patch.object(module, "load_jev_snapshot", AsyncMock(return_value=snapshot)),
            patch.object(module, "choose_many_with_jev", native),
            patch.object(module, "record_action", AsyncMock()),
        ):
            violation = await module.judge_guarded_values(manifest.name, args, request=request)
    finally:
        current_tracker.reset(token)
    return violation, native


async def test_a_place_on_an_address_parameter_passes() -> None:
    violation, native = await _judge({"destination": "Gare de Lyon, Paris"}, [_answer("place")])
    assert violation is None
    state = native.await_args.kwargs["state"]
    assert state["value"] == "Gare de Lyon, Paris"
    assert state["query"] == "Itinéraire vers chez Marc"
    assert state["parameter"] == {
        "tool": "get_route_tool",
        "name": "destination",
        "semantic_type": "physical_address",
        "description": "destination value",
    }


async def test_a_name_typed_by_the_person_is_refused() -> None:
    violation, _ = await _judge({"destination": "Sophie Martin"}, [_answer("person_name")])
    assert violation is not None
    assert (violation.param_name, violation.value_kind) == ("destination", "person_name")
    assert "person's name" in violation.llm_message()


async def test_a_phone_number_in_an_email_slot_is_refused_with_its_kind() -> None:
    mail = _manifest([("to", "string", "email_address")])
    violation, _ = await _judge({"to": "06 12 34 56 78"}, [_answer("phone_number")], manifest=mail)
    assert violation is not None and violation.value_kind == "phone_number"
    assert "a phone number" in violation.llm_message()
    assert "person's name" not in violation.llm_message()


async def test_free_text_on_a_location_is_never_refused() -> None:
    violation, _ = await _judge({"destination": "Visio"}, [_answer("other")])
    assert violation is None


async def test_anything_but_an_address_is_refused_on_an_email_parameter() -> None:
    mail = _manifest([("to", "string", "email_address")])
    violation, _ = await _judge({"to": "Banque Populaire"}, [_answer("other")], manifest=mail)
    assert violation is not None and violation.value_kind == "other"


async def test_a_meeting_link_is_a_valid_event_location() -> None:
    violation, _ = await _judge({"destination": "https://meet.example.test/abc"}, [_answer("link")])
    assert violation is None


@pytest.mark.parametrize(
    "attempt",
    [
        DecisionAttempt(outcome="timeout"),
        DecisionAttempt(outcome="invalid_response"),
        DecisionAttempt(outcome="success"),
    ],
)
async def test_a_failed_judgment_refuses_nothing(attempt: DecisionAttempt) -> None:
    violation, _ = await _judge({"destination": "Sophie Martin"}, [attempt])
    assert violation is None


async def test_an_uncertain_judgment_refuses_nothing() -> None:
    below = max(0.0, JEV_PARAMETER_KIND_MIN_CONFIDENCE - 0.01)
    violation, _ = await _judge({"destination": "Sophie Martin"}, [_answer("person_name", below)])
    assert violation is None


async def test_switched_off_asks_nothing() -> None:
    violation, native = await _judge({"destination": "Sophie Martin"}, [], requested=False)
    assert violation is None
    native.assert_not_awaited()


@pytest.mark.parametrize(
    ("request_text", "tracker"),
    [
        (None, TRACKER),
        ("  ", TRACKER),
        ("q", None),
        ("q", SimpleNamespace(user_id=OWNER, run_id="")),
    ],
)
async def test_no_request_or_no_owner_asks_nothing(
    request_text: str | None, tracker: object
) -> None:
    violation, native = await _judge(
        {"destination": "Sophie Martin"}, [], request=request_text, tracker=tracker
    )
    assert violation is None
    native.assert_not_awaited()


async def test_a_value_a_selected_field_proves_is_not_judged() -> None:
    violation, native = await _judge({"destination": "Sophie Martin"}, [], proven=True)
    assert violation is None
    native.assert_not_awaited()


async def test_a_repeated_value_is_judged_once() -> None:
    attendees = _manifest([("attendees", "array", "email_address")])
    violation, native = await _judge(
        {"attendees": ["ada@example.test", "ada@example.test"]},
        [_answer("email_address")],
        manifest=attendees,
    )
    assert violation is None
    assert native.await_count == 1


async def test_an_unguarded_call_asks_nothing() -> None:
    plain = _manifest([("query", "string", "Text")])
    violation, native = await _judge({"query": "Sophie Martin"}, [], manifest=plain)
    assert violation is None
    native.assert_not_awaited()


async def test_every_list_value_is_judged_up_to_the_bound() -> None:
    attendees = _manifest([("attendees", "array", "email_address")])
    values = [f"p{i}@example.test" for i in range(JEV_PARAMETER_KIND_MAX_VALUES + 3)]
    answers = [_answer("email_address")] * JEV_PARAMETER_KIND_MAX_VALUES
    violation, native = await _judge({"attendees": values}, answers, manifest=attendees)
    assert violation is None
    assert native.await_count == JEV_PARAMETER_KIND_MAX_VALUES


async def test_the_first_refused_value_is_reported() -> None:
    attendees = _manifest([("attendees", "array", "email_address")])
    violation, _ = await _judge(
        {"attendees": ["ada@example.test", "Grace Hopper"]},
        [_answer("email_address"), _answer("person_name")],
        manifest=attendees,
    )
    assert violation is not None and violation.value == "Grace Hopper"


async def test_an_unexpected_error_fails_open() -> None:
    violation, _ = await _judge({"destination": "Sophie Martin"}, RuntimeError("boom"))
    assert violation is None


async def test_cancellation_is_never_swallowed() -> None:
    with pytest.raises(asyncio.CancelledError):
        await _judge({"destination": "Sophie Martin"}, asyncio.CancelledError())


def test_the_question_offers_exactly_the_kinds_the_code_reads() -> None:
    question = json.loads(load_prompt("jev_parameter_kind_question", version="v1"))
    assert tuple(question["criteria"]) == module.VALUE_KINDS
    assert set(module.ACCEPTED_VALUE_KINDS) == set(GUARDED_SEMANTIC_TYPES)
    for accepted in module.ACCEPTED_VALUE_KINDS.values():
        assert accepted <= set(module.VALUE_KINDS)

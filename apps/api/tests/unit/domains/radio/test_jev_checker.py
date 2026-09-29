"""Native checks keep the radio editor's whole-script and fallback contracts."""

import importlib
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.radio.facts import FactKind, FactPack, RadioFact, Sensitivity, SourceRef
from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.script import LineKind, RadioDelivery, ScriptPart
from src.domains.radio.verification import VerifiedLine
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer

pytestmark = pytest.mark.unit

PACK = FactPack(
    format=RadioFormat.BULLETIN,
    facts=(
        RadioFact(
            id="n1",
            kind=FactKind.NEWS,
            text="The council rejected the proposal.",
            key="news:1",
            sensitivity=Sensitivity.PUBLIC,
            source=SourceRef(label="Example News"),
        ),
    ),
)
LINES = (
    VerifiedLine(
        RadioRole.ANCHOR,
        ScriptPart.INTRO,
        LineKind.TRANSITION,
        "Welcome to Radio 42.",
        RadioDelivery(),
        (),
    ),
    VerifiedLine(
        RadioRole.ANCHOR,
        ScriptPart.BODY,
        LineKind.FACT,
        "The council rejected the proposal.",
        RadioDelivery(),
        ("n1",),
    ),
    VerifiedLine(
        RadioRole.ANCHOR,
        ScriptPart.BODY,
        LineKind.FACT,
        "The council approved the proposal.",
        RadioDelivery(),
        ("n1",),
    ),
)


def decision(choice: str, confidence: float = 0.999) -> ChoiceAnswer:
    return ChoiceAnswer(
        type="choice",
        choice=choice,
        confidence=confidence,
        probabilities={
            key: 0.998 if key == choice else 0.001
            for key in ("supported", "unsupported", "unknown")
        },
    )


async def test_complete_native_script_maps_exact_positions_and_never_checks_transitions() -> None:
    module = importlib.import_module("src.domains.radio.jev_checker")
    fallback = AsyncMock()
    with patch.object(
        module,
        "choose_many_with_jev",
        AsyncMock(
            return_value=DecisionAttempt(
                outcome="success",
                answers={"line1": decision("supported"), "line2": decision("unsupported")},
            )
        ),
    ) as native:
        checker = module.JevLineChecker(
            fallback, user_id=uuid4(), run_id="radio", station_name="Radio 42"
        )
        assert await checker.unsupported(LINES, PACK) == frozenset({2})
    fallback.unsupported.assert_not_awaited()
    sent = native.call_args.kwargs
    assert sent["state"]["station"] == "Radio 42"
    assert len(sent["questions"]) == 2
    assert sent["state"]["facts"][0]["text"] == PACK.facts[0].text


@pytest.mark.parametrize(
    "lines",
    [
        (LINES[1],) * 25,
        (replace(LINES[1], text="界" * 12000),),
        (replace(LINES[1], refs=("missing",)),),
    ],
)
async def test_unrepresentable_script_uses_whole_original_without_native_spend(lines) -> None:
    module = importlib.import_module("src.domains.radio.jev_checker")
    fallback = AsyncMock()
    fallback.unsupported.return_value = None
    with patch.object(module, "choose_many_with_jev", AsyncMock()) as native:
        checker = module.JevLineChecker(
            fallback, user_id=uuid4(), run_id="radio", station_name="Radio 42"
        )
        assert await checker.unsupported(lines, PACK) is None
    native.assert_not_awaited()
    fallback.unsupported.assert_awaited_once_with(lines, PACK)


@pytest.mark.parametrize(
    "attempt",
    [
        DecisionAttempt(outcome="disabled"),
        DecisionAttempt(outcome="timeout"),
        DecisionAttempt(outcome="success", answers={"line1": decision("supported")}),
        DecisionAttempt(
            outcome="success",
            answers={"line1": decision("supported"), "line2": decision("unknown")},
        ),
        DecisionAttempt(
            outcome="success",
            answers={"line1": decision("supported", 0.8), "line2": decision("unsupported")},
        ),
    ],
)
async def test_any_uncertainty_checks_the_original_whole_script_once(attempt) -> None:
    module = importlib.import_module("src.domains.radio.jev_checker")
    fallback = AsyncMock()
    fallback.unsupported.return_value = frozenset({1})
    with patch.object(module, "choose_many_with_jev", AsyncMock(return_value=attempt)):
        checker = module.JevLineChecker(
            fallback, user_id=uuid4(), run_id="radio", station_name="Radio 42"
        )
        assert await checker.unsupported(LINES, PACK) == frozenset({1})
    fallback.unsupported.assert_awaited_once_with(LINES, PACK)


async def test_transition_only_script_spends_nothing() -> None:
    module = importlib.import_module("src.domains.radio.jev_checker")
    fallback = AsyncMock()
    with patch.object(module, "choose_many_with_jev", AsyncMock()) as native:
        checker = module.JevLineChecker(
            fallback, user_id=uuid4(), run_id="radio", station_name="Radio 42"
        )
        assert await checker.unsupported(LINES[:1], PACK) == frozenset()
    native.assert_not_awaited()
    fallback.unsupported.assert_not_awaited()


async def test_native_verdict_flows_through_the_existing_deterministic_editor() -> None:
    from src.domains.radio.production import ProductionLimits, WritingRequest, _checked_script
    from src.domains.radio.verification import VerificationResult
    from tests.unit.domains.radio.test_checking import DRAFT
    from tests.unit.domains.radio.test_checking import PACK as EDITOR_PACK

    module = importlib.import_module("src.domains.radio.jev_checker")
    request = WritingRequest(
        format=RadioFormat.BULLETIN,
        pack=EDITOR_PACK,
        language="en",
        local_now=datetime(2026, 9, 29, tzinfo=UTC),
        station_id=False,
        station_name="Radio 42",
    )
    fallback = AsyncMock()
    with patch.object(
        module,
        "choose_many_with_jev",
        AsyncMock(
            return_value=DecisionAttempt(
                outcome="success",
                answers={
                    f"line{n}": decision("unsupported" if n == 3 else "supported")
                    for n in range(1, 6)
                },
            )
        ),
    ):
        result = await _checked_script(
            DRAFT,
            request,
            limits=ProductionLimits(120, 2, 10, 1, 1),
            checker=module.JevLineChecker(
                fallback, user_id=uuid4(), run_id="radio", station_name="Radio 42"
            ),
        )
    assert isinstance(result, VerificationResult) and result.accepted
    assert [ref for line in result.lines for ref in line.refs] == ["n1", "n2", "n4", "n5"]
    assert len(result.origins) == len(result.lines)
    fallback.unsupported.assert_not_awaited()

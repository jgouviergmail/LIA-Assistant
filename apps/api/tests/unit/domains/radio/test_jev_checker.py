"""Native checks keep the radio editor's whole-script and fallback contracts."""

import importlib
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.constants import JEV_SHARED_STATE_BATCH_BYTES
from src.domains.radio.facts import FactKind, FactPack, RadioFact, Sensitivity, SourceRef
from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.script import LineKind, RadioDelivery, ScriptPart
from src.domains.radio.verification import VerifiedLine
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import NoulAnswer

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


def decision(verdict: str) -> NoulAnswer:
    """A decided line: the Noul is the probability of an UNSUPPORTED claim."""
    return NoulAnswer(type="noul", noul=0.999 if verdict == "unsupported" else 0.001)


def undecided(probability: float) -> NoulAnswer:
    return NoulAnswer(type="noul", noul=probability)


async def test_complete_native_script_maps_exact_positions_and_never_checks_transitions() -> None:
    module = importlib.import_module("src.domains.radio.jev_checker")
    fallback = AsyncMock()
    with patch.object(
        module,
        "choose_many_with_jev",
        AsyncMock(
            return_value=DecisionAttempt(
                outcome="success",
                nouls={"line1": decision("supported"), "line2": decision("unsupported")},
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


@pytest.mark.parametrize("reason", ["too_many_lines", "request_too_large", "missing_references"])
async def test_unrepresentable_script_uses_whole_original_without_native_spend(reason) -> None:
    module = importlib.import_module("src.domains.radio.jev_checker")
    # Relative to the bounds the checker enforces (a CJK character is 3 UTF-8 bytes).
    lines = {
        "too_many_lines": (LINES[1],) * (module.MAX_CHECKED_LINES + 1),
        "request_too_large": (
            replace(LINES[1], text="界" * (JEV_SHARED_STATE_BATCH_BYTES // 3 + 1)),
        ),
        "missing_references": (replace(LINES[1], refs=("missing",)),),
    }[reason]
    fallback = AsyncMock()
    fallback.unsupported.return_value = None
    with (
        patch.object(module, "choose_many_with_jev", AsyncMock()) as native,
        patch.object(module, "jev_decisions_total") as counted,
    ):
        checker = module.JevLineChecker(
            fallback, user_id=uuid4(), run_id="radio", station_name="Radio 42"
        )
        assert await checker.unsupported(lines, PACK) is None
    native.assert_not_awaited()
    fallback.unsupported.assert_awaited_once_with(lines, PACK)
    # A script handed back before any call is counted under its closed reason.
    counted.labels.assert_called_once_with(usage=module.JevUsage.RADIO_VERIFICATION, outcome=reason)


@pytest.mark.parametrize(
    "attempt",
    [
        DecisionAttempt(outcome="disabled"),
        DecisionAttempt(outcome="timeout"),
        DecisionAttempt(outcome="success", nouls={"line1": decision("supported")}),
        DecisionAttempt(
            outcome="success",
            nouls={"line1": decision("supported"), "line2": undecided(0.5)},
        ),
        DecisionAttempt(
            outcome="success",
            nouls={"line1": undecided(0.3), "line2": decision("unsupported")},
        ),
        DecisionAttempt(
            outcome="success",
            nouls={"line1": decision("supported"), "line2": undecided(0.7)},
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
                nouls={
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


async def test_a_line_exactly_at_the_margin_is_decided_and_just_past_it_is_not() -> None:
    module = importlib.import_module("src.domains.radio.jev_checker")
    margin = module.DECISION_MARGIN

    async def judged(first: float, second: float) -> frozenset[int] | None:
        fallback = AsyncMock()
        fallback.unsupported.return_value = None
        attempt = DecisionAttempt(
            outcome="success", nouls={"line1": undecided(first), "line2": undecided(second)}
        )
        with patch.object(module, "choose_many_with_jev", AsyncMock(return_value=attempt)):
            checker = module.JevLineChecker(
                fallback, user_id=uuid4(), run_id="radio", station_name="Radio 42"
            )
            return await checker.unsupported(LINES, PACK)

    assert await judged(margin, 1 - margin) == frozenset({2})
    assert await judged(margin + 0.01, 1 - margin) is None
    assert await judged(margin, 1 - margin - 0.01) is None


async def test_lines_are_asked_as_nouls_naming_their_own_line() -> None:
    module = importlib.import_module("src.domains.radio.jev_checker")
    request = module.verifier_request(LINES, PACK, "Radio 42")
    assert request is not None
    _, questions = request
    assert set(questions) == {"line1", "line2"}
    for key, question in questions.items():
        assert question.type == "noul"
        assert isinstance(question.instructions, dict)
        assert f"`script.{key}`" in str(question.instructions["question"])

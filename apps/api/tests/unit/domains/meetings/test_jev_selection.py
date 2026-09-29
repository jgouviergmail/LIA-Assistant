"""Jev never chooses an unowned candidate or replaces the existing uncertainty path."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.meetings import jev_selection as module
from src.infrastructure.llm.decision_types import DecisionAttempt, DecisionCharge
from src.infrastructure.llm.typesafe_client import ChoiceAnswer
from tests.unit.domains.meetings.test_template_resolution import DEFAULT, MEDICAL

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def record_charge(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    writer = AsyncMock()
    monkeypatch.setattr(module, "record_selection_charge", writer)
    return writer


@pytest.mark.parametrize(
    "choice,confidence,selected",
    [
        ("c1", 0.99, True),
        ("c1", 0.94, False),
        ("none", 0.99, False),
        ("invented", 1.0, False),
    ],
)
async def test_only_a_confident_owned_choice_survives(
    choice: str, confidence: float, selected: bool
) -> None:
    charge = DecisionCharge(
        model="jev-1.13.0", input_tokens=500, output_tokens=3, cost_usd=0.000021, cost_eur=0.0000189
    )
    answer = ChoiceAnswer(
        type="choice", choice=choice, confidence=confidence, probabilities={choice: 1.0}
    )
    with patch.object(
        module,
        "choose_with_jev",
        AsyncMock(return_value=DecisionAttempt(answer, charge, "success")),
        create=True,
    ) as choose:
        result = await module.select_template_with_jev(
            meeting_id=uuid4(),
            user_id=uuid4(),
            run_id="meeting-test",
            candidates=[DEFAULT, MEDICAL],
            excerpt="Le médecin examine le traitement.",
            calendar_title="Consultation",
        )
    assert (result.template == MEDICAL) is selected
    assert result.charge == charge
    question = choose.await_args.kwargs["question"]
    assert set(question.criteria) == {"c0", "c1", "none"}
    assert "For doctors." in question.criteria["c1"]
    assert "builtin:" not in str(question.criteria)
    assert choose.await_args.kwargs["state"]["transcript_excerpt"].startswith("Le médecin")


async def test_no_candidates_spends_nothing() -> None:
    with patch.object(module, "choose_with_jev", AsyncMock(), create=True) as choose:
        result = await module.select_template_with_jev(
            meeting_id=uuid4(),
            user_id=uuid4(),
            run_id="meeting-test",
            candidates=[],
            excerpt="x",
            calendar_title=None,
        )
    assert result.template is None and result.charge is None
    choose.assert_not_awaited()

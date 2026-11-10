"""An observer's verdict is filed beside what its extractor itself proposed (ADR-374, D.2).

The extractor states what its own parse kept (``set_proposals``); the observer never
re-implements four parsers. An output nobody can read counts as proposing — a failure
is never read as « nothing to extract » — and an extractor that stopped before it
parsed leaves no agreement row at all: nothing can be compared.
"""

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.time_utils import now_utc
from src.domains.agents.services import jev_extraction_observer as module
from src.domains.llm_config import jev_statistics_sink as sink_module
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_statistics_sink import JevStatisticsSink
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer

pytestmark = pytest.mark.unit

USAGE = JevUsage.OBSERVE_MEMORY


@pytest.fixture(autouse=True)
def sink() -> Iterator[JevStatisticsSink]:
    fresh = JevStatisticsSink()
    with patch.object(sink_module, "_SINK", fresh):
        yield fresh


def _attempt(
    choice: str = "empty", outcome: str = "success", probabilities: dict[str, float] | None = None
) -> DecisionAttempt:
    if outcome != "success":
        return DecisionAttempt(outcome=outcome)
    answer = ChoiceAnswer(
        type="choice",
        choice=choice,
        confidence=0.9,
        probabilities=probabilities or {choice: 0.9, "useful": 0.1},
    )
    return DecisionAttempt(outcome="success", answer=answer)


async def _observe(attempt: DecisionAttempt, output: str | None, proposals: int | None) -> None:
    with (
        patch.object(module, "choose_with_jev", AsyncMock(return_value=attempt)),
        patch.object(module, "record_action", AsyncMock()),
    ):
        async with module.observe_extraction(USAGE, str(uuid4()), "run", "prompt") as observed:
            if output is not None:
                observed.set_output(output)
            if proposals is not None:
                observed.set_proposals(proposals)


def _agreement(sink: JevStatisticsSink) -> dict[tuple[str, int, bool], int]:
    return {
        (verdict, bucket, proposed): count
        for (day, usage, verdict, bucket, proposed), count in sink.take().agreement.items()
        if usage == USAGE.value and day == now_utc().date()
    }


@pytest.mark.parametrize(
    ("output", "proposals", "proposed"),
    [
        ("[]", 0, False),
        ("```json\n[]\n```", 0, False),
        ('{"items": []}', 0, False),
        ('[{"action":"create","content":"x"}]', 1, True),
        ("I could not decide what to extract.", 0, True),
    ],
    ids=["empty-list", "fenced-empty", "empty-object", "one-proposal", "unreadable"],
)
async def test_the_verdict_is_filed_beside_what_the_extractor_proposed(
    sink: JevStatisticsSink, output: str, proposals: int, proposed: bool
) -> None:
    await _observe(_attempt("empty"), output, proposals)
    # The verdict's confidence is choice_confidence: the provider's 0.90 bounded by the
    # concentration (2 × 0.90 − 1) / (2 − 1) = 0.80.
    assert _agreement(sink) == {("empty", 80, proposed): 1}


async def test_a_verdict_without_a_computable_confidence_files_no_agreement(
    sink: JevStatisticsSink,
) -> None:
    await _observe(_attempt("empty", probabilities={"empty": 1.0}), "[]", 0)
    assert _agreement(sink) == {}


async def test_an_extractor_that_stopped_before_parsing_files_no_agreement(
    sink: JevStatisticsSink,
) -> None:
    await _observe(_attempt("useful"), "[]", None)
    assert _agreement(sink) == {}


async def test_a_failed_observation_files_its_outcome_and_no_agreement(
    sink: JevStatisticsSink,
) -> None:
    await _observe(_attempt(outcome="timeout"), "[]", 0)
    batch = sink.take()
    assert batch.agreement == {}
    assert batch.outcomes == {(now_utc().date(), USAGE.value, "timeout"): 1}


async def test_a_successful_observation_counts_as_observed(sink: JevStatisticsSink) -> None:
    await _observe(_attempt("useful"), "[]", 0)
    assert sink.take().outcomes == {(now_utc().date(), USAGE.value, "observed"): 1}

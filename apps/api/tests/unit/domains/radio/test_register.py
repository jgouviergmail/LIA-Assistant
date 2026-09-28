"""What the transparency register keeps of the radio (ADR-263, ADR-324 decision 31).

A session is ONE act the listener started, and a translated article another: one
row each in the decision register, filed under the run their euros and their
consultations are already filed under — never an action, since nothing of the
person's changed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from src.domains.agents.effects.decisions import TurnDecision
from src.domains.agents.effects.models import DecisionOutcome
from src.domains.radio import register as module
from src.domains.radio.session import EndReason

pytestmark = pytest.mark.unit

LISTENER = UUID("00000000-0000-4000-8000-0000000000d1")
STARTED = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)


@pytest.fixture
def filed(monkeypatch: pytest.MonkeyPatch) -> list[TurnDecision]:
    rows: list[TurnDecision] = []

    async def record_once(decision: TurnDecision) -> None:
        rows.append(decision)

    monkeypatch.setattr(module, "record_decision_once", record_once)
    return rows


def test_every_way_a_session_ends_reads_as_an_outcome() -> None:
    assert set(module.END_OUTCOMES) == set(EndReason)


class TestASession:
    async def test_is_one_act_the_listener_started_filed_under_its_run(
        self, filed: list[TurnDecision]
    ) -> None:
        await module.file_session(
            user_id=LISTENER, run_id="radio_abc", started_at=STARTED, reason=EndReason.TIMER
        )

        [row] = filed
        assert (row.run_id, row.thread_id, row.user_id) == ("radio_abc", "radio_abc", LISTENER)
        assert (row.source, row.execution_mode, row.route) == ("user", "direct", "radio")
        assert row.started_at == STARTED
        assert (row.outcome, row.stop_reason) == (DecisionOutcome.ANSWERED, None)

    @pytest.mark.parametrize(
        ("reason", "outcome"),
        [
            (EndReason.LISTENER, DecisionOutcome.ANSWERED),
            (EndReason.IDLE, DecisionOutcome.INTERRUPTED),
            (EndReason.BUDGET, DecisionOutcome.INTERRUPTED),
            (EndReason.FAILURES, DecisionOutcome.FAILED),
        ],
    )
    async def test_an_end_before_the_plan_says_why(
        self, filed: list[TurnDecision], reason: EndReason, outcome: DecisionOutcome
    ) -> None:
        await module.file_session(
            user_id=LISTENER, run_id="radio_abc", started_at=STARTED, reason=reason
        )

        [row] = filed
        assert (row.outcome, row.stop_reason) == (outcome, reason.value)


class TestAnArticle:
    @pytest.mark.parametrize(
        ("translated", "outcome"),
        [(True, DecisionOutcome.ANSWERED), (False, DecisionOutcome.FAILED)],
    )
    async def test_a_translation_that_ran_is_an_act_of_its_own(
        self, filed: list[TurnDecision], translated: bool, outcome: DecisionOutcome
    ) -> None:
        await module.file_article(
            user_id=LISTENER,
            run_id="radio_article_1",
            started_at=STARTED,
            translated=translated,
        )

        [row] = filed
        assert (row.run_id, row.thread_id) == ("radio_article_1", "radio_article_1")
        assert (row.source, row.execution_mode, row.route) == ("user", "direct", "radio_article")
        assert (row.started_at, row.outcome) == (STARTED, outcome)

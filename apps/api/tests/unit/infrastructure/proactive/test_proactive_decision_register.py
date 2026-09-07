"""A turn that ran outside the graph is still a turn (ADR-263 amendment).

Measured 2026-09-07 on production, joining ``token_usage_logs`` to
``agent_decisions`` by ``run_id``: every conversational surface was recorded —
24/24, 22/22, 10/10, 8/8, 7/7, 6/6 — while **228 proactive runs produced not a
single row**. Nothing was failing. The registers follow the GRAPH, and these
surfaces call the model directly, so they never entered the code that records.

The consequence for the account holder is the part that matters: the briefing
reads their mail, their calendar and their tasks every morning, at their
expense, and their register said nothing had happened since the last
conversation.

``track_proactive_tokens`` is the single funnel all thirteen of those call
sites already use, and it is called with the totals once the work is done —
exactly when a turn's row can be written, the write being an upsert on
``run_id`` anyway. So the register joins the accounting rather than growing a
second seam beside it.

The funnel is named for the plumbing, NOT for the initiative, and conflating
the two was a defect caught before shipping: nothing schedules the briefing, so
filing every caller as ``proactive`` would have credited LIA with page loads it
never chose to make. Each site declares its own authorship
(``test_out_of_turn_source_declaration``).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.effects.models import EffectSource

pytestmark = [pytest.mark.unit]


def _fake_tracking_context() -> object:
    """A ``TrackingContext`` that accepts the calls and records nothing.

    The cost half is proven elsewhere; pinning it again here would make this
    file fail for a reason it is not about.
    """

    class _Tracker:
        async def __aenter__(self) -> _Tracker:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def record_node_tokens(self, **_: object) -> None:
            return None

        async def commit(self) -> None:
            return None

    def _factory(**_: object) -> _Tracker:
        return _Tracker()

    return _factory


class TestProactiveSpendReachesTheDecisionRegister:
    """Work done outside the graph is written down like anything else."""

    async def test_a_tracked_out_of_turn_run_records_its_turn(self) -> None:
        from src.infrastructure.proactive.tracking import track_proactive_tokens

        recorded: list[object] = []

        with (
            patch("src.domains.chat.service.TrackingContext", _fake_tracking_context()),
            patch(
                "src.domains.agents.effects.decision_recorder.record_decision",
                AsyncMock(side_effect=lambda decision: recorded.append(decision)),
            ),
        ):
            run_id = await track_proactive_tokens(
                user_id=uuid.uuid4(),
                task_type="briefing",
                target_id="target-1234567890",
                conversation_id=None,
                tokens_in=500,
                tokens_out=150,
                model_name="gpt-5.6-luna",
                source=EffectSource.USER.value,
            )

        assert run_id is not None
        assert len(recorded) == 1, "a proactive run left no row in the decision register"
        assert recorded[0].run_id == run_id, "the row must be filed under the run that spent"

    async def test_a_runner_sweep_is_recorded_as_an_initiative(self) -> None:
        """``proactive`` is a THIRD origin, and it is narrow on purpose.

        A routine is the person's own instruction, deferred; a briefing answers
        a request. Only a surface LIA itself decided to run — the heartbeat
        sweep, the interest sweeps, the weekly self-reflection — is an
        initiative. Verified by reading the call graph on 2026-09-07: nothing
        schedules the briefing, so filing it here would have credited LIA with
        a page load it never chose to make.
        """
        from src.domains.agents.effects.models import EffectSource
        from src.infrastructure.proactive.tracking import track_proactive_tokens

        recorded: list[object] = []

        with (
            patch("src.domains.chat.service.TrackingContext", _fake_tracking_context()),
            patch(
                "src.domains.agents.effects.decision_recorder.record_decision",
                AsyncMock(side_effect=lambda decision: recorded.append(decision)),
            ),
        ):
            await track_proactive_tokens(
                user_id=uuid.uuid4(),
                task_type="heartbeat",
                target_id="target-1234567890",
                conversation_id=None,
                tokens_in=10,
                tokens_out=10,
                model_name="gpt-5.6-luna",
                source=EffectSource.PROACTIVE.value,
            )

        assert recorded[0].source == EffectSource.PROACTIVE.value

    async def test_a_run_that_spent_nothing_records_nothing(self) -> None:
        """No spend, no turn: the eligibility sweep must not fill the register.

        ``track_proactive_tokens`` already returns early on zero tokens, and
        that early exit is what keeps a register readable — a sweep that
        decides not to act did nothing worth telling its owner about.
        """
        from src.infrastructure.proactive.tracking import track_proactive_tokens

        recorded: list[object] = []

        with patch(
            "src.domains.agents.effects.decision_recorder.record_decision",
            AsyncMock(side_effect=lambda decision: recorded.append(decision)),
        ):
            result = await track_proactive_tokens(
                user_id=uuid.uuid4(),
                task_type="heartbeat",
                target_id="target-1234567890",
                conversation_id=None,
                tokens_in=0,
                tokens_out=0,
                source=EffectSource.PROACTIVE.value,
            )

        assert result is None
        assert recorded == []

    async def test_a_failing_register_never_costs_the_accounting(self) -> None:
        """Observing must not break what it observes.

        The cost is already spent when this runs, and the provider has already
        billed it. A register that raises here would lose the euro it came to
        describe — the exact inversion of what it is for.
        """
        from src.infrastructure.proactive.tracking import track_proactive_tokens

        with (
            patch("src.domains.chat.service.TrackingContext", _fake_tracking_context()),
            patch(
                "src.domains.agents.effects.decision_recorder.record_decision",
                AsyncMock(side_effect=RuntimeError("register down")),
            ),
        ):
            run_id = await track_proactive_tokens(
                user_id=uuid.uuid4(),
                task_type="briefing",
                target_id="target-1234567890",
                conversation_id=None,
                tokens_in=500,
                tokens_out=150,
                model_name="gpt-5.6-luna",
                source=EffectSource.USER.value,
            )

        assert run_id is not None, "a broken register must not swallow the run id"

"""How a turn's verdict is DERIVED, not asked for (ADR-263, lot 6).

The register's whole value rests on one property: a turn that did not answer
must never read as one that did. Asking callers to say so is how that property
rots — there is always one more exit path someone forgets. So the recorder
derives it from what actually happened, and these are the cases it must get
right.

The collector's shape is the lot-4 lesson, re-applied: a LIVE object the
parent publishes, never a value a child sets. A ``ContextVar.set()`` inside a
child task does not reach its parent — it works in ReAct, where the loop runs
in the parent's context, and silently loses every pipeline turn.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.effects.decision_recorder import decision_recorder
from src.domains.agents.effects.decisions import (
    TurnDecision,
    current_turn,
    note_answered,
    note_plan,
    note_request_message,
    note_route,
)
from src.domains.agents.effects.models import DecisionOutcome

pytestmark = [pytest.mark.unit]


@dataclass
class _Session:
    commit: AsyncMock


async def test_one_shot_record_survives_cancellation_without_starting_a_second_write() -> None:
    from src.domains.agents.effects import decision_recorder as module

    entered, release = asyncio.Event(), asyncio.Event()
    completed: list[bool] = []

    async def write(decision: TurnDecision, *, once: bool = False) -> None:
        entered.set()
        await release.wait()
        completed.append(once)

    with patch.object(module, "_write_logged", write):
        task = asyncio.create_task(module.record_decision_once(_turn()))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert completed == [True]


def _turn(**overrides: object) -> TurnDecision:
    base: dict[str, object] = {
        "run_id": f"run-{uuid.uuid4().hex[:8]}",
        "user_id": uuid.uuid4(),
        "thread_id": "thread-A",
        "execution_mode": "pipeline",
    }
    base.update(overrides)
    return TurnDecision(**base)  # type: ignore[arg-type]


class TestTheVerdictIsDERIVED:
    async def test_a_turn_that_says_nothing_is_INTERRUPTED(self) -> None:
        """A HITL interrupt ends the turn without an answer. That is a fact,
        not an absence — and certainly not a success."""
        decision = _turn()

        with patch("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock()):
            async with decision_recorder(decision):
                pass

        assert decision.outcome is DecisionOutcome.INTERRUPTED

    async def test_an_answered_turn_is_ANSWERED(self) -> None:
        decision = _turn()

        with patch("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock()):
            async with decision_recorder(decision):
                note_answered(uuid.uuid4())

        assert decision.outcome is DecisionOutcome.ANSWERED
        assert decision.response_message_id is not None

    async def test_a_raising_turn_is_FAILED(self) -> None:
        decision = _turn()

        with (
            patch("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock()),
            pytest.raises(RuntimeError),
        ):
            async with decision_recorder(decision):
                raise RuntimeError("the provider went away")

        assert decision.outcome is DecisionOutcome.FAILED

    async def test_a_CANCELLED_turn_stays_interrupted_rather_than_failed(self) -> None:
        """A user closing their tab is not an error, and calling it one would
        put a failure on every abandoned turn."""
        decision = _turn()

        with (
            patch("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock()),
            pytest.raises(asyncio.CancelledError),
        ):
            async with decision_recorder(decision):
                raise asyncio.CancelledError

        assert decision.outcome is DecisionOutcome.INTERRUPTED

    async def test_an_explicit_success_is_never_DOWNGRADED_by_a_late_failure(self) -> None:
        """The answer was delivered; a stream breaking during teardown must not
        rewrite the turn as one the user got nothing from."""
        decision = _turn()

        with (
            patch("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock()),
            pytest.raises(RuntimeError),
        ):
            async with decision_recorder(decision):
                note_answered(uuid.uuid4())
                raise RuntimeError("the stream broke after the answer")

        assert decision.outcome is DecisionOutcome.ANSWERED


class TestTheRowIsWrittenWHATEVERHappens:
    @pytest.mark.parametrize("failing", [False, True])
    async def test_the_turn_is_written_on_both_paths(self, failing: bool) -> None:
        decision = _turn()
        write = AsyncMock()

        with patch("src.domains.agents.effects.decision_recorder._write_shielded", write):
            if failing:
                with pytest.raises(RuntimeError):
                    async with decision_recorder(decision):
                        raise RuntimeError("boom")
            else:
                async with decision_recorder(decision):
                    pass

        write.assert_awaited_once_with(decision)

    async def test_a_turn_with_no_account_writes_NOTHING(self) -> None:
        """A probe, a boot check, a test harness: nothing to record, and
        nobody to record it for."""
        from src.domains.agents.effects import decision_recorder as module

        # The repository is imported lazily inside ``_write``; patching it at
        # its home is what proves the guard fires BEFORE the import, which is
        # also what keeps a probe from opening a database session.
        with patch(
            "src.domains.agents.effects.decision_repository.DecisionRepository"
        ) as repository:
            await module._write(_turn(user_id=None))

        repository.assert_not_called()


class TestARunFiledOnce:
    """An out-of-turn act that cannot be resumed is filed ONCE (ADR-263 amendment 2026-09-27)."""

    @staticmethod
    def _database() -> tuple[object, list[_Session]]:
        sessions: list[_Session] = []

        @contextlib.asynccontextmanager
        async def get_db_context() -> AsyncIterator[_Session]:
            session = _Session(commit=AsyncMock())
            sessions.append(session)
            yield session

        return get_db_context, sessions

    async def test_it_writes_through_the_insert_that_ignores_a_second_filing(self) -> None:
        from src.domains.agents.effects import decision_recorder as module

        get_db_context, sessions = self._database()
        decision = _turn()
        with (
            patch(
                "src.domains.agents.effects.decision_repository.DecisionRepository"
            ) as repository,
            patch("src.infrastructure.database.session.get_db_context", get_db_context),
        ):
            repository.return_value.record_once = AsyncMock()
            repository.return_value.record = AsyncMock()
            await module.record_decision_once(decision)

        repository.assert_called_once_with(sessions[0])
        repository.return_value.record_once.assert_awaited_once()
        assert repository.return_value.record_once.await_args.args == (decision,)
        repository.return_value.record.assert_not_awaited()
        sessions[0].commit.assert_awaited_once()

    async def test_a_failed_write_is_logged_never_raised(self) -> None:
        from src.domains.agents.effects import decision_recorder as module

        get_db_context, sessions = self._database()
        with (
            patch(
                "src.domains.agents.effects.decision_repository.DecisionRepository"
            ) as repository,
            patch("src.infrastructure.database.session.get_db_context", get_db_context),
        ):
            repository.return_value.record_once = AsyncMock(side_effect=RuntimeError("down"))
            await module.record_decision_once(_turn())

        repository.return_value.record_once.assert_awaited_once()
        sessions[0].commit.assert_not_awaited()

    async def test_a_run_with_no_account_writes_nothing(self) -> None:
        from src.domains.agents.effects import decision_recorder as module

        with patch(
            "src.domains.agents.effects.decision_repository.DecisionRepository"
        ) as repository:
            await module.record_decision_once(_turn(user_id=None))

        repository.assert_not_called()


class TestTheCollectorIsAROUNDTheTurn:
    async def test_a_note_from_a_CHILD_TASK_reaches_the_parent(self) -> None:
        """The lot-4 lesson, re-applied. A `ContextVar.set()` in a child task
        does not reach its parent — publishing an OBJECT and mutating it does,
        which is what makes one implementation serve pipeline and ReAct."""
        decision = _turn()

        async def a_node() -> None:
            note_route("planner")
            note_plan(4)

        with patch("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock()):
            async with decision_recorder(decision):
                await asyncio.create_task(a_node())

        assert (decision.route, decision.plan_step_count) == ("planner", 4)

    async def test_a_note_OUTSIDE_a_turn_is_silent(self) -> None:
        """These helpers run in tests, scripts and probes; raising there would
        turn an observability concern into an outage."""
        assert current_turn() is None

        note_route("planner")
        note_plan(2)
        note_request_message(uuid.uuid4())
        note_answered(uuid.uuid4())

    async def test_the_turn_is_unpublished_once_it_ends(self) -> None:
        """Otherwise the next turn on the same task would enrich the last one."""
        decision = _turn()

        with patch("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock()):
            async with decision_recorder(decision):
                assert current_turn() is decision

        assert current_turn() is None

    async def test_the_engine_is_filed_beside_what_was_asked(self) -> None:
        """An automatic turn files the engine the router chose AND the request:
        « auto » alone would say nothing of what ran, the engine alone nothing
        of what the person asked for (ADR-390)."""
        from src.domains.agents.effects.decisions import note_engine, turn_decision

        decision = turn_decision(
            run_id="r", user_id=uuid.uuid4(), thread_id="t", execution_mode="auto", automated=False
        )

        async def the_router() -> None:
            note_engine("pipeline", "direct")

        with patch("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock()):
            async with decision_recorder(decision):
                await asyncio.create_task(the_router())

        assert (decision.execution_mode, decision.requested_mode, decision.resolution_reason) == (
            "pipeline",
            "auto",
            "direct",
        )

    @pytest.mark.parametrize(
        ("requested", "settled", "badge"),
        [
            ("auto", "pipeline", "pipeline"),
            ("auto", "react", "react"),
            ("auto", None, None),  # a conversation: no engine planned it
            ("react", "react", None),  # an explicit choice needs no badge
            ("pipeline", "pipeline", None),
        ],
    )
    async def test_only_an_automatic_turn_names_its_engine(
        self, requested: str, settled: str | None, badge: str | None
    ) -> None:
        """The answer's badge (ADR-390) says what « auto » chose, and only that."""
        from src.domains.agents.effects.decisions import (
            automatic_turn_engine,
            note_engine,
            turn_decision,
        )

        decision = turn_decision(
            run_id="r",
            user_id=uuid.uuid4(),
            thread_id="t",
            execution_mode=requested,
            automated=False,
        )
        with patch("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock()):
            async with decision_recorder(decision):
                if settled is not None:
                    note_engine(settled, "requested")
                answered = automatic_turn_engine()

        assert answered == badge
        assert automatic_turn_engine() is None, "outside a turn there is nothing to name"

    async def test_a_resumed_turn_names_the_engine_it_started_with(self) -> None:
        """A resumed segment never meets the router: the builder settles its engine
        from the state, and its answer keeps the badge — the reason stays the first
        segment's, never invented."""
        from src.domains.agents.context.runtime_context_builder import build_runtime_context
        from src.domains.agents.effects.decisions import automatic_turn_engine, turn_decision
        from tests.fixtures.conversation_cases import conversation_target

        decision = turn_decision(
            run_id="r", user_id=uuid.uuid4(), thread_id="t", execution_mode="auto", automated=False
        )
        with patch("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock()):
            async with decision_recorder(decision):
                build_runtime_context(
                    state={"messages": [], "execution_mode": "react"},  # type: ignore[arg-type]
                    target=conversation_target(uuid.uuid4(), uuid.uuid4()),
                    user_execution_mode="auto",
                    resuming=True,
                )
                answered = automatic_turn_engine()

        assert answered == "react"
        assert decision.resolution_reason is None

    async def test_a_turn_no_engine_planned_keeps_what_was_asked(self) -> None:
        """A conversation, or a turn that stopped before the router."""
        from src.domains.agents.effects.decisions import turn_decision

        decision = turn_decision(
            run_id="r", user_id=uuid.uuid4(), thread_id="t", execution_mode="auto", automated=False
        )

        assert (decision.execution_mode, decision.requested_mode, decision.resolution_reason) == (
            "auto",
            "auto",
            None,
        )

    async def test_a_missing_pointer_never_BLANKS_one_already_known(self) -> None:
        decision = _turn()
        known = uuid.uuid4()

        with patch("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock()):
            async with decision_recorder(decision):
                note_request_message(known)
                note_request_message(None)

        assert decision.request_message_id == known

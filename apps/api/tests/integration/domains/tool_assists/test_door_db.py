"""An assist's traces, on a real PostgreSQL (ADR-372).

A unit test can say the door called the ledger; only the database can say that the spend, the
decision and the read of one click land on one run, under the account and the slot that answered,
and that an answer already held leaves nothing at all. The rows are written by the door's own
sessions, so the person is committed, then removed.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

import src.domains.agents.effects.treatment_recorder  # noqa: F401  installs the collector
import src.domains.agents.effects.treatments  # noqa: F401  installs the sink
from src.domains.agents.effects.models import AgentDecision, AgentTreatment
from src.domains.chat.models import TokenUsageLog
from src.domains.tool_assists import door
from src.domains.tool_assists.catalogue import ToolAssist
from src.domains.tool_assists.door import AssistRun, run_assist
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

pytestmark = pytest.mark.integration


def _spent(run: AssistRun) -> None:
    """A model answered: what the provider reports reaches the run's callback."""
    usage = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
    message = AIMessage(content="ok", usage_metadata=usage)
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    for handler in run.config["callbacks"]:
        handler.on_llm_end(result, run_id=uuid4())


@pytest.fixture
async def person(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[UUID]:
    """An account the door's own sessions can see, its ceilings open."""

    async def open_ceilings(user_id: object, *, layer: str) -> None:
        return None

    monkeypatch.setattr(door, "enforce_usage_limit", open_ceilings)
    monkeypatch.setattr(door, "slot_model", lambda slot: "a-model")
    user_id = uuid4()
    async with get_db_context() as db:
        db.add(
            User(
                id=user_id,
                email=f"assist-{user_id.hex[:8]}@test.local",
                hashed_password="x",
                is_active=True,
                is_superuser=False,
                full_name="Assist Reader",
            )
        )
    yield user_id
    async with get_db_context() as db:
        for model in (AgentTreatment, AgentDecision, TokenUsageLog):
            await db.execute(delete(model).where(model.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))


def _words(row: Sequence[object]) -> tuple[str, ...]:
    """A row as text, an enum by its stored value."""
    return tuple(str(getattr(value, "value", value)) for value in row)


async def _rows(user_id: UUID) -> dict[str, list[tuple[str, ...]]]:
    # The read's batch is written in a shielded task of its own: let it land.
    await asyncio.sleep(0.2)
    async with get_db_context() as db:
        spend = await db.execute(
            select(TokenUsageLog.run_id, TokenUsageLog.llm_type, TokenUsageLog.prompt_tokens).where(
                TokenUsageLog.user_id == user_id
            )
        )
        decided = await db.execute(
            select(AgentDecision.run_id, AgentDecision.source).where(
                AgentDecision.user_id == user_id
            )
        )
        reads = await db.execute(
            select(AgentTreatment.run_id, AgentTreatment.tool_name, AgentTreatment.outcome).where(
                AgentTreatment.user_id == user_id
            )
        )
        return {
            "spend": [_words(row) for row in spend.all()],
            "decisions": [_words(row) for row in decided.all()],
            "reads": [_words(row) for row in reads.all()],
        }


async def test_a_click_leaves_its_spend_its_decision_and_its_read_on_one_run(
    person: UUID,
) -> None:
    async def answering(run: AssistRun) -> str:
        async with run.reading():
            _spent(run)
        return "the answer"

    done = await run_assist(ToolAssist.MAIL_REPLY, person, "fr", answering)

    assert done.value == "the answer"
    rows = await _rows(person)
    (spend,) = rows["spend"]
    (decision,) = rows["decisions"]
    (read,) = rows["reads"]
    assert spend[1:] == ("email_agent", "100")
    assert decision == (spend[0], "user")
    assert read == (spend[0], "tool_assist:mail", "ok")


async def test_what_was_read_by_sight_is_on_the_slot_that_read_it(person: UUID) -> None:
    async def by_sight(run: AssistRun) -> str:
        run.slot = "vision_analysis"
        _spent(run)
        return "the reading"

    await run_assist(ToolAssist.FILE_SUMMARY, person, "fr", by_sight)

    (spend,) = (await _rows(person))["spend"]
    assert spend[1] == "vision_analysis"


async def test_an_answer_already_held_leaves_nothing(person: UUID) -> None:
    async def held(run: AssistRun) -> str:
        return "the digest"

    done = await run_assist(ToolAssist.MAIL_SUMMARY, person, "fr", held)

    assert done.usage is None
    assert await _rows(person) == {"spend": [], "decisions": [], "reads": []}

"""Reset business metrics follow real commits, not mocked method invocations."""

from uuid import UUID, uuid4

import pytest
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_target import ConversationKind
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.conversations.models import Conversation
from src.infrastructure.observability.metrics import conversation_length_messages
from src.infrastructure.observability.metrics_agents import conversation_resets_total
from src.infrastructure.observability.metrics_business import (
    conversation_abandonment_at_message_count,
    conversation_abandonment_total,
    conversation_tokens_total,
)
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


def _value(metric: Counter | Histogram, suffix: str) -> float:
    """Read the public collector instead of relying on private metric internals."""
    return float(
        next(
            sample.value
            for family in metric.collect()
            for sample in family.samples
            if sample.name.endswith(suffix)
        )
    )


def _snapshot() -> dict[str, float]:
    return {
        "resets": _value(conversation_resets_total, "_total"),
        "length": _value(conversation_length_messages, "_sum"),
        "abandoned": _value(
            conversation_abandonment_total.labels(
                abandonment_reason="user_reset", agent_type="generic"
            ),
            "_total",
        ),
        "messages": _value(
            conversation_abandonment_at_message_count.labels(abandonment_reason="user_reset"),
            "_sum",
        ),
        "tokens": _value(conversation_tokens_total.labels(agent_type="generic"), "_sum"),
    }


async def _conversation(
    engine: AsyncEngine, owners: list[UUID], messages: int, tokens: int
) -> UUID:
    owner = await commit_owner(engine, owners)
    async with AsyncSession(engine) as db:
        db.add(
            Conversation(
                id=owner,
                user_id=owner,
                runtime_id=owner,
                kind=ConversationKind.MAIN,
                title="Metrics fixture",
                message_count=messages,
                total_tokens=tokens,
            )
        )
        await db.commit()
    return owner


@pytest.mark.parametrize(("messages", "tokens"), [(0, 0), (0, 10), (1, 0), (4, 27)])
async def test_metrics_record_first_commit_only(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    messages: int,
    tokens: int,
) -> None:
    owner = await _conversation(async_engine, committed_user_ids, messages, tokens)
    before, request = _snapshot(), uuid4()
    async with AsyncSession(async_engine) as db:
        service = ConversationLifecycle(db)
        await service.request_reset(owner, owner, operation_id=request, expected_revision=0)
        once = _snapshot()
        assert once == {
            "resets": before["resets"] + 1,
            "length": before["length"] + messages,
            "abandoned": before["abandoned"] + int(messages > 0),
            "messages": before["messages"] + messages,
            "tokens": before["tokens"] + (tokens if messages else 0),
        }
        await service.request_reset(owner, owner, operation_id=request, expected_revision=0)
        assert _snapshot() == once


async def test_rolled_back_reset_records_no_metric(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _conversation(async_engine, committed_user_ids, 4, 27)
    before = _snapshot()
    async with AsyncSession(async_engine) as db:

        async def refuse_commit() -> None:
            raise RuntimeError("Injected rollback")

        monkeypatch.setattr(db, "commit", refuse_commit)
        with pytest.raises(RuntimeError, match="Injected"):
            await ConversationLifecycle(db).request_reset(
                owner, owner, operation_id=uuid4(), expected_revision=0
            )
        assert _snapshot() == before

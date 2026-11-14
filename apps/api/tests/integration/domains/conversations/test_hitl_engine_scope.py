"""The actual streaming writer and decision reader agree on the admitted runtime."""

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Interrupt, interrupt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.conversation_execution import RunAdmission
from src.core.exceptions import CacheError, DatabaseError
from src.domains.agents.api.hitl_pending import clear_completed_interrupt
from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.services.orchestration.approval_decision import (
    HitlDecisionStaleError,
    parse_approval_decision,
)
from src.domains.agents.services.orchestration.service import OrchestrationService
from src.domains.agents.services.streaming.service import StreamingService
from src.domains.agents.utils.hitl_store import HITLStore
from src.domains.conversations.runtime_identity import checkpoint_config
from src.infrastructure.database import session
from src.infrastructure.streaming.run_admission import owned_execution

pytestmark = pytest.mark.integration


async def test_streaming_question_keeps_public_business_identity_but_persists_runtime(
    reserved: RunAdmission,
    redis_client: Redis,
) -> None:
    store = HITLStore(redis_client, 30)
    service = StreamingService(hitl_store=store)
    interrupt = Interrupt(
        value={
            "action_requests": [
                {"type": "tool_confirmation", "name": "test_tool", "user_message": "Confirm?"}
            ],
            "user_language": "en",
        },
        id="question-1",
    )
    async with owned_execution(reserved):
        chunks = [
            chunk
            async for chunk in service._handle_hitl_interrupt(
                {"__interrupt__": [interrupt]},
                reserved.target,
                reserved.run_id,
            )
        ]
        metadata = next(
            chunk.metadata for chunk in chunks if chunk.type == "hitl_interrupt_metadata"
        )
        assert metadata is not None and metadata["conversation_id"] == str(reserved.target.id)
        pending = await store.get_pending(str(reserved.target.runtime_id))
        assert pending is not None and pending["run_id"] == reserved.run_id
        assert await store.get_pending(str(reserved.target.id)) is None


@pytest.mark.parametrize("structured", [False, True])
async def test_real_graph_loader_resumes_the_runtime_question(
    reserved: RunAdmission,
    redis_client: Redis,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    structured: bool,
) -> None:
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )

    async def ask(state: MessagesState) -> dict[str, object]:
        interrupt({"question": "Confirm?"})
        return {}

    builder = StateGraph(MessagesState)
    builder.add_node("ask", ask)
    builder.add_edge(START, "ask")
    builder.add_edge("ask", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    initial = create_initial_state(
        reserved.target.owner_id,
        "session",
        reserved.run_id,
        user_timezone="UTC",
        user_language="en",
    )
    initial["messages"] = [HumanMessage(content="A request")]
    store = HITLStore(redis_client, 30)
    async with owned_execution(reserved):
        await graph.ainvoke(initial, checkpoint_config(reserved.target))
        await store.save_interrupt(
            str(reserved.target.runtime_id),
            {
                "run_id": reserved.run_id,
                "message_id": "question-1",
                "action_requests": [{"type": "tool_confirmation", "name": "test_tool"}],
            },
        )
        state = await OrchestrationService().load_or_create_state(
            graph,
            reserved.target,
            "yes",
            "session",
            reserved.run_id,
            "UTC",
            "en",
            [],
            is_hitl_resumption=True,
            hitl_decision={"message_id": "question-1", "action": "confirm"} if structured else None,
        )
        assert state.get("_interrupt_resume_data") == {"action": "confirm", "_user_message": "yes"}


async def test_a_lost_approval_read_cannot_turn_yes_into_a_fresh_request(
    reserved: RunAdmission,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(self: HITLStore, thread_id: str) -> None:
        raise ConnectionError("Test approval read failed")

    async with owned_execution(reserved):
        monkeypatch.setattr(HITLStore, "get_interrupt", unavailable)
        with pytest.raises(CacheError):
            await parse_approval_decision("yes", reserved.target.runtime_id, reserved.run_id, "en")


@pytest.mark.parametrize("acknowledged_delete", [False, True])
async def test_a_completed_graph_cannot_resume_a_question_after_lost_cleanup(
    reserved: RunAdmission,
    redis_client: Redis,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    acknowledged_delete: bool,
) -> None:
    """A stale Redis question never replays an act the checkpoint already finished."""
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    performed: list[str] = []

    async def ask(state: MessagesState) -> dict[str, object]:
        answer = interrupt({"question": "Confirm?"})
        performed.append(answer)
        return {}

    builder = StateGraph(MessagesState)
    builder.add_node("ask", ask)
    builder.add_edge(START, "ask")
    builder.add_edge("ask", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    initial = create_initial_state(
        reserved.target.owner_id,
        "session",
        reserved.run_id,
        user_timezone="UTC",
        user_language="en",
    )
    initial["messages"] = [HumanMessage(content="A request")]
    store = HITLStore(redis_client, 30)
    async with owned_execution(reserved):
        config = checkpoint_config(reserved.target)
        await graph.ainvoke(initial, config)
        await store.save_interrupt(
            str(reserved.target.runtime_id),
            {
                "run_id": reserved.run_id,
                "message_id": "question-1",
                "action_requests": [{"type": "tool_confirmation", "name": "test_tool"}],
            },
        )
        await graph.ainvoke(Command(resume="confirmed"), config)
        assert performed == ["confirmed"]
        assert not (await graph.aget_state(config)).tasks
        original_clear = HITLStore.clear_interrupt

        async def lost_ack(self: HITLStore, thread_id: str) -> None:
            if acknowledged_delete:
                await original_clear(self, thread_id)
            raise ConnectionError("Test cleanup unavailable or acknowledgement lost")

        with monkeypatch.context() as fault:
            fault.setattr(HITLStore, "clear_interrupt", lost_ack)
            with pytest.raises(ConnectionError):
                await clear_completed_interrupt(reserved.target)
        with pytest.raises(HitlDecisionStaleError):
            await OrchestrationService().load_or_create_state(
                graph,
                reserved.target,
                "yes",
                "session",
                reserved.run_id,
                "UTC",
                "en",
                [],
                is_hitl_resumption=True,
            )
        assert await store.get_pending(str(reserved.target.runtime_id)) is None
        assert performed == ["confirmed"]


@pytest.mark.parametrize("resuming", [False, True])
async def test_a_failed_checkpoint_read_preserves_the_question_and_refuses_a_new_state(
    reserved: RunAdmission,
    redis_client: Redis,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    resuming: bool,
) -> None:
    """A failed read is neither an empty history nor evidence of completion."""
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    builder = StateGraph(MessagesState)
    builder.add_edge(START, END)
    graph = builder.compile(checkpointer=InMemorySaver())
    store = HITLStore(redis_client, 30)

    async def unavailable(config: object) -> None:
        raise ConnectionError("Test checkpoint read unavailable")

    async with owned_execution(reserved):
        await store.save_interrupt(
            str(reserved.target.runtime_id),
            {
                "run_id": reserved.run_id,
                "message_id": "question-1",
                "action_requests": [{"type": "tool_confirmation", "name": "test_tool"}],
            },
        )
        before = await store.get_pending(str(reserved.target.runtime_id))
        monkeypatch.setattr(graph, "aget_state", unavailable)
        with pytest.raises(DatabaseError):
            await OrchestrationService().load_or_create_state(
                graph,
                reserved.target,
                "yes",
                "session",
                reserved.run_id,
                "UTC",
                "en",
                [],
                is_hitl_resumption=resuming,
            )
        assert await store.get_pending(str(reserved.target.runtime_id)) == before

"""Real native checkpoint writes cannot outlive their conversation generation."""

import asyncio
from collections.abc import AsyncIterator
from typing import TypedDict
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from langchain_core.embeddings import Embeddings
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, empty_checkpoint
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import GetOp, Item, PutOp, Result, SearchOp
from langgraph.types import Command, interrupt
from psycopg import AsyncConnection, sql
from psycopg.rows import DictRow, dict_row
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.tool_context_scope import (
    ChildToolContextScope,
    tool_context_namespace,
    voice_context_id,
)
from src.domains.conversations.instrumented_checkpointer import InstrumentedAsyncPostgresSaver
from src.domains.conversations.models import Conversation
from src.domains.conversations.runtime_identity import checkpoint_config, checkpoint_identity
from src.domains.conversations.runtime_store import RuntimeAsyncPostgresStore
from src.domains.users.models import User
from tests.fixtures.persisted_runtimes import admitted_runtime

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def persisted_target(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> AsyncIterator[ConversationRef]:
    """Keep account, business identity and runtime deliberately distinct."""
    target = ConversationRef(uuid4(), uuid4(), ConversationKind.SECONDARY, 7, uuid4())
    committed_user_ids.append(target.owner_id)
    async with AsyncSession(async_engine) as db:
        db.add(
            User(
                id=target.owner_id,
                email=f"runtime-{target.owner_id}@example.test",
                hashed_password="unused",
                is_active=True,
            )
        )
        await db.flush()
        db.add(
            Conversation(
                id=target.id,
                user_id=target.owner_id,
                title="Runtime isolation",
                kind=target.kind,
                revision=target.revision,
                runtime_id=target.runtime_id,
            )
        )
        await db.commit()
    yield target


@pytest_asyncio.fixture
async def runtime_target(
    async_engine: AsyncEngine, persisted_target: ConversationRef
) -> AsyncIterator[ConversationRef]:
    """Ordinary native writes run within a genuine committed graph admission."""
    async with admitted_runtime(async_engine, persisted_target):
        yield persisted_target


def target_config(target: ConversationRef) -> RunnableConfig:
    """The public graph contract, independent of the persistence implementation."""
    return checkpoint_config(target)


def checkpoint() -> Checkpoint:
    """Exercise blob serialization as well as the checkpoint row."""
    value = empty_checkpoint()
    value["channel_values"] = {"evidence": {"values": [1, 2, 3]}}
    value["channel_versions"] = {"evidence": 1}
    return value


METADATA: CheckpointMetadata = {"source": "update", "step": 0, "parents": {}}


@pytest.mark.parametrize("pending", [False, True])
async def test_retired_generation_cannot_recreate_native_storage(
    native_connection: AsyncConnection[DictRow],
    runtime_target: ConversationRef,
    async_engine: AsyncEngine,
    pending: bool,
) -> None:
    """A late checkpoint or pending write after purge is explicitly refused."""
    saver = InstrumentedAsyncPostgresSaver(native_connection)
    config = target_config(runtime_target)
    saved = await saver.aput(config, checkpoint(), METADATA, {"evidence": 1})
    # Retain identity even on the old adapter, so RED measures the missing fence.
    saved = {"configurable": {**config["configurable"], **saved["configurable"]}}
    try:
        async with AsyncSession(async_engine) as db:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == runtime_target.id)
                .values(runtime_id=uuid4(), revision=runtime_target.revision + 1)
            )
            await db.commit()
        await saver.adelete_thread(str(runtime_target.runtime_id))
        with pytest.raises(RuntimeError, match="runtime"):
            if pending:
                await saver.aput_writes(saved, [("result", {"late": True})], "late-task")
            else:
                await saver.aput(config, checkpoint(), METADATA, {"evidence": 1})
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            # Static table vocabulary, parameterized private identity.
            cursor = await native_connection.execute(
                sql.SQL("SELECT count(*) AS n FROM {} WHERE thread_id = %s").format(
                    sql.Identifier(table)
                ),
                (str(runtime_target.runtime_id),),
            )
            assert (await cursor.fetchone()) == {"n": 0}
    finally:
        await saver.adelete_thread(str(runtime_target.runtime_id))


async def test_native_round_trip_preserves_identity_and_outer_rollback(
    native_connection: AsyncConnection[DictRow], runtime_target: ConversationRef
) -> None:
    """Returned and restored configs carry the same immutable target."""
    saver = InstrumentedAsyncPostgresSaver(native_connection)
    config = target_config(runtime_target)
    try:
        saved = await saver.aput(config, checkpoint(), METADATA, {"evidence": 1})
        assert checkpoint_identity(saved).conversation_id == runtime_target.id
        assert checkpoint_identity(saved).revision == runtime_target.revision
        await saver.aput_writes(saved, [("answer", {"ok": True})], "first-task")
        loaded = await saver.aget_tuple(config)
        assert loaded is not None and loaded.pending_writes
        assert loaded.checkpoint["channel_values"]["evidence"] == {"values": [1, 2, 3]}
        assert checkpoint_identity(loaded.config).conversation_id == runtime_target.id
        await saver.adelete_thread(str(runtime_target.runtime_id))
        with pytest.raises(ValueError, match="rollback"):
            async with native_connection.transaction():
                saved = await saver.aput(config, checkpoint(), METADATA, {"evidence": 1})
                await saver.aput_writes(saved, [("answer", {"ok": True})], "rolled-back")
                raise ValueError("rollback")
        assert await saver.aget_tuple(config) is None
        cursor = await native_connection.execute(
            "SELECT count(*) AS n FROM checkpoint_blobs WHERE thread_id = %s",
            (str(runtime_target.runtime_id),),
        )
        assert (await cursor.fetchone()) == {"n": 0}
    finally:
        await saver.adelete_thread(str(runtime_target.runtime_id))


@pytest.mark.parametrize(
    "field", ["user_id", "conversation_id", "conversation_revision", "thread_id"]
)
async def test_forged_or_incomplete_scope_never_writes(
    native_connection: AsyncConnection[DictRow], runtime_target: ConversationRef, field: str
) -> None:
    """Matching a runtime alone does not authorize another owner or generation."""
    saver = InstrumentedAsyncPostgresSaver(native_connection)
    config = target_config(runtime_target)
    scope = (
        config["configurable"] if field == "thread_id" else config["configurable"]["runtime_scope"]
    )
    scope[field] = -1 if field == "conversation_revision" else str(uuid4())
    try:
        with pytest.raises((RuntimeError, ValueError), match="runtime|identity"):
            await saver.aput(config, checkpoint(), METADATA, {"evidence": 1})
    finally:
        await saver.adelete_thread(str(config["configurable"]["thread_id"]))


async def test_reset_waits_for_the_same_transaction_as_native_writes(
    native_connection: AsyncConnection[DictRow],
    runtime_target: ConversationRef,
    test_database_url_sync: str,
) -> None:
    """An incompatible update cannot slip between the fence and native commit."""
    saver = InstrumentedAsyncPostgresSaver(native_connection)
    config = target_config(runtime_target)
    async with await AsyncConnection.connect(
        test_database_url_sync, autocommit=True, row_factory=dict_row
    ) as other:

        async def rotate() -> None:
            await other.execute(
                "UPDATE conversations SET runtime_id = %s, revision = revision + 1 WHERE id = %s",
                (uuid4(), runtime_target.id),
            )

        task: asyncio.Task[None] | None = None
        try:
            async with native_connection.transaction():
                await saver.aput(config, checkpoint(), METADATA, {"evidence": 1})
                task = asyncio.create_task(rotate())
                async with asyncio.timeout(5):
                    while True:
                        cursor = await native_connection.execute(
                            "SELECT cardinality(pg_blocking_pids(%s)) AS n",
                            (other.info.backend_pid,),
                        )
                        row = await cursor.fetchone()
                        if row is not None and row["n"] > 0:
                            break
                        assert not task.done(), "Reset crossed an uncommitted native write"
                        await asyncio.sleep(0.01)
            await task
        finally:
            if task is not None and not task.done():
                task.cancel()
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
            await saver.adelete_thread(str(runtime_target.runtime_id))


@pytest.mark.parametrize("synchronous", [False, True])
async def test_runtime_store_writes_cannot_resurrect_a_retired_generation(
    native_connection: AsyncConnection[DictRow],
    runtime_target: ConversationRef,
    async_engine: AsyncEngine,
    synchronous: bool,
) -> None:
    """Both native API forms enter the same SQL fence; cleanup can still delete."""
    store = RuntimeAsyncPostgresStore(native_connection)
    namespace = (str(runtime_target.owner_id), str(runtime_target.runtime_id), "context", "event")
    try:
        await store.aput(namespace, "list", {"items": [1]}, index=False)
        assert (await store.aget(namespace, "list")) is not None
        async with AsyncSession(async_engine) as db:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == runtime_target.id)
                .values(runtime_id=uuid4(), revision=runtime_target.revision + 1)
            )
            await db.commit()
        await store.adelete(namespace, "list")
        with pytest.raises(RuntimeError, match="runtime"):
            if synchronous:
                await asyncio.to_thread(store.put, namespace, "list", {"items": [2]}, index=False)
            else:
                await store.aput(namespace, "list", {"items": [2]}, index=False)
        assert (await store.aget(namespace, "list")) is None
    finally:
        await store.adelete(namespace, "list")
        if store._task is not None:
            store._task.cancel()
            await asyncio.gather(store._task, return_exceptions=True)


async def test_tool_context_requires_unindexed_storage(
    native_connection: AsyncConnection[DictRow], runtime_target: ConversationRef
) -> None:
    """Tool state must never launch a paid embedding inside its write transaction."""
    store = RuntimeAsyncPostgresStore(native_connection)
    namespace = (str(runtime_target.owner_id), str(runtime_target.runtime_id), "context", "event")
    try:
        with pytest.raises(ValueError, match="index=False"):
            await store.aput(namespace, "list", {"items": [1]})
    finally:
        await store.adelete(namespace, "list")
        if store._task is not None:
            store._task.cancel()
            await asyncio.gather(store._task, return_exceptions=True)


async def test_mixed_store_batch_keeps_results_and_both_scopes(
    native_connection: AsyncConnection[DictRow], runtime_target: ConversationRef
) -> None:
    """A batch does not confuse account learning with conversation working state."""
    store = RuntimeAsyncPostgresStore(native_connection)
    account = (str(runtime_target.owner_id), "memories")
    runtime = (str(runtime_target.owner_id), str(runtime_target.runtime_id), "context", "event")
    try:
        assert await store.abatch(
            [
                PutOp(runtime, "list", {"items": [1]}, index=False),
                PutOp(account, "proof", {"fact": "account"}, index=False),
            ]
        ) == [None, None]
        results = await store.abatch([GetOp(account, "proof"), GetOp(runtime, "list")])
        assert isinstance(results[0], Item) and results[0].value == {"fact": "account"}
        assert isinstance(results[1], Item) and results[1].value == {"items": [1]}
    finally:
        await store.adelete(account, "proof")
        await store.adelete(runtime, "list")
        if store._task is not None:
            store._task.cancel()
            await asyncio.gather(store._task, return_exceptions=True)


class _QuestionState(TypedDict):
    """Small deterministic graph, with a real nested interrupt and checkpoint."""

    question: str
    answer: str


async def test_two_histories_resume_nested_hitl_independently_and_rotation_starts_empty(
    native_connection: AsyncConnection[DictRow],
    persisted_target: ConversationRef,
    async_engine: AsyncEngine,
) -> None:
    """Real graph subgraphs carry scope through save, load and pending writes."""
    runtime_target = persisted_target
    second = ConversationRef(
        runtime_target.owner_id, uuid4(), ConversationKind.SECONDARY, 0, uuid4()
    )
    async with AsyncSession(async_engine) as db:
        db.add(
            Conversation(
                id=second.id,
                user_id=second.owner_id,
                kind=second.kind,
                revision=second.revision,
                runtime_id=second.runtime_id,
                title="Other history",
            )
        )
        await db.commit()

    def ask(state: _QuestionState) -> dict[str, str]:
        answer = interrupt(state["question"])
        assert isinstance(answer, str)
        return {"answer": answer}

    child = StateGraph(_QuestionState)
    child.add_node("ask", ask)
    child.add_edge(START, "ask")
    child.add_edge("ask", END)
    parent = StateGraph(_QuestionState)
    parent.add_node("question", child.compile())
    parent.add_edge(START, "question")
    parent.add_edge("question", END)
    saver = InstrumentedAsyncPostgresSaver(native_connection)
    graph = parent.compile(checkpointer=saver)
    second_config = checkpoint_config(second)
    next_runtime = uuid4()
    try:
        async with admitted_runtime(async_engine, runtime_target):
            await graph.ainvoke({"question": "A", "answer": ""}, checkpoint_config(runtime_target))
        async with admitted_runtime(async_engine, second):
            await graph.ainvoke({"question": "B", "answer": ""}, checkpoint_config(second))
        async with admitted_runtime(async_engine, runtime_target):
            first = await graph.ainvoke(
                Command(resume="approved A"), checkpoint_config(runtime_target)
            )
        assert first["question"] == "A" and first["answer"] == "approved A"
        waiting = await graph.aget_state(second_config)
        assert waiting.values["question"] == "B" and waiting.values["answer"] == ""
        assert waiting.tasks and waiting.tasks[0].interrupts
        async with admitted_runtime(async_engine, second):
            second_result = await graph.ainvoke(
                Command(resume="refused B"), checkpoint_config(second)
            )
        assert second_result["question"] == "B" and second_result["answer"] == "refused B"
        async with AsyncSession(async_engine) as db:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == runtime_target.id)
                .values(
                    runtime_id=next_runtime,
                    revision=runtime_target.revision + 1,
                )
            )
            await db.commit()
        new_target = ConversationRef(
            runtime_target.owner_id,
            runtime_target.id,
            runtime_target.kind,
            runtime_target.revision + 1,
            next_runtime,
        )
        fresh = await graph.aget_state(checkpoint_config(new_target))
        assert not fresh.values and not fresh.tasks
        # Rotation does not change any other conversation's restored history.
        other = await graph.aget_state(second_config)
        assert other.values["answer"] == "refused B"
    finally:
        for runtime_id in (runtime_target.runtime_id, second.runtime_id, next_runtime):
            await saver.adelete_thread(str(runtime_id))


async def test_store_shutdown_cancels_and_joins_a_blocked_write(
    native_connection: AsyncConnection[DictRow],
    runtime_target: ConversationRef,
    test_database_url_sync: str,
) -> None:
    """Closing the Store owns both the SQL operation and the vendor's idle task."""
    store = RuntimeAsyncPostgresStore(native_connection)
    namespace = (str(runtime_target.owner_id), str(runtime_target.runtime_id), "context", "event")
    async with await AsyncConnection.connect(
        test_database_url_sync, autocommit=True, row_factory=dict_row
    ) as blocker:
        task: asyncio.Task[None] | None = None
        try:
            async with blocker.transaction():
                await blocker.execute(
                    "SELECT id FROM conversations WHERE id = %s FOR UPDATE", (runtime_target.id,)
                )
                task = asyncio.create_task(
                    store.aput(namespace, "list", {"items": [1]}, index=False)
                )
                async with asyncio.timeout(5):
                    while True:
                        cursor = await blocker.execute(
                            "SELECT cardinality(pg_blocking_pids(%s)) AS n",
                            (native_connection.info.backend_pid,),
                        )
                        row = await cursor.fetchone()
                        if row is not None and row["n"]:
                            break
                        assert not task.done()
                        await asyncio.sleep(0.01)
                await store.aclose()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert store._task is not None and store._task.done()
                assert not store._active_batches
                with pytest.raises(RuntimeError, match="closed"):
                    await store.aput(namespace, "list", {"items": [2]}, index=False)
        finally:
            if task is not None and not task.done():
                task.cancel()
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
            await store.aclose()


class _SlowEmbeddings(Embeddings):
    """A controlled asynchronous provider, with synchronous I/O deliberately refused."""

    def __init__(self, started: asyncio.Event, release: asyncio.Event) -> None:
        self.started = started
        self.release = release

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("The Store must use the asynchronous provider")

    def embed_query(self, text: str) -> list[float]:
        raise AssertionError("The Store must use the asynchronous provider")

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.started.set()
        await self.release.wait()
        return [[1.0, 0.0, 0.0] for _ in texts]


async def test_mixed_semantic_batch_holds_no_runtime_transaction_while_embedding(
    native_connection: AsyncConnection[DictRow],
    runtime_target: ConversationRef,
    test_database_url_sync: str,
) -> None:
    """Observe PostgreSQL while a real native Store waits on a controlled embedder."""
    started, release = asyncio.Event(), asyncio.Event()

    schema = f"runtime_embedding_{uuid4().hex}"
    await native_connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    await native_connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    seed = RuntimeAsyncPostgresStore(native_connection)
    try:
        # Create the native base tables in isolation before exposing public's
        # vector extension. Otherwise IF NOT EXISTS would adopt public.store.
        await seed.setup()
    finally:
        await seed.aclose()
    await native_connection.execute(
        sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema))
    )
    store = RuntimeAsyncPostgresStore(
        native_connection,
        index={"dims": 3, "embed": _SlowEmbeddings(started, release), "fields": ["fact"]},
    )
    runtime = (str(runtime_target.owner_id), str(runtime_target.runtime_id), "context", "event")
    account = (str(runtime_target.owner_id), "memories")
    task: asyncio.Task[list[Result]] | None = None
    try:
        # A private schema prevents test index dimensions contaminating other suites.
        await store.setup()
        await native_connection.execute(
            sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema))
        )
        await store.aput(runtime, "list", {"items": [1]}, index=False)
        task = asyncio.create_task(
            store.abatch(
                [
                    GetOp(runtime, "list"),
                    SearchOp(account, query="account fact", limit=1),
                    PutOp(account, "proof", {"fact": "semantic account memory"}),
                    PutOp(runtime, "list", {"items": [2]}, index=False),
                ]
            )
        )
        async with asyncio.timeout(5):
            await started.wait()
        async with await AsyncConnection.connect(
            test_database_url_sync, autocommit=True, row_factory=dict_row
        ) as observer:
            cursor = await observer.execute(
                "SELECT state, xact_start FROM pg_stat_activity WHERE pid = %s",
                (native_connection.info.backend_pid,),
            )
            row = await cursor.fetchone()
            assert row == {"state": "idle", "xact_start": None}
            # A separate heartbeat stays responsive while the model stand-in waits.
            async with asyncio.timeout(2):
                await observer.execute("SELECT 1")
        release.set()
        result = await task
        assert len(result) == 4 and result[1:] == [[], None, None]
        assert isinstance(result[0], Item) and result[0].value == {"items": [1]}
        item = await store.aget(runtime, "list")
        assert item is not None and item.value == {"items": [2]}
        memory = await store.aget(account, "proof")
        assert memory is not None and memory.value == {"fact": "semantic account memory"}
        matches = await store.asearch(account, query="account fact", limit=1)
        assert len(matches) == 1 and matches[0].key == "proof"
    finally:
        release.set()
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await store.aclose()
        await native_connection.execute("SET search_path TO public")
        await native_connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
        )


@pytest.mark.parametrize("delete_last", [True, False])
async def test_runtime_batch_preserves_native_last_put_wins(
    native_connection: AsyncConnection[DictRow],
    runtime_target: ConversationRef,
    delete_last: bool,
) -> None:
    """Splitting a batch by scope must not reverse put/delete deduplication."""
    store = RuntimeAsyncPostgresStore(native_connection)
    namespace = (str(runtime_target.owner_id), str(runtime_target.runtime_id), "context", "event")
    put = PutOp(namespace, "list", {"items": [1]}, index=False)
    remove = PutOp(namespace, "list", None)
    try:
        ops = [put, remove] if delete_last else [remove, put]
        assert await store.abatch(ops) == [None, None]
        item = await store.aget(namespace, "list")
        if delete_last:
            assert item is None
        else:
            assert item is not None and item.value == {"items": [1]}
    finally:
        await store.adelete(namespace, "list")
        await store.aclose()


async def test_child_context_stays_discoverable_under_only_its_parent_runtime(
    native_connection: AsyncConnection[DictRow], runtime_target: ConversationRef
) -> None:
    """A synthetic child never creates an unowned purge namespace."""
    store = RuntimeAsyncPostgresStore(native_connection)
    owner = str(runtime_target.owner_id)
    child = ChildToolContextScope(runtime_target.runtime_id, "research-child")
    namespace = tool_context_namespace(owner, child, "event")
    try:
        await store.aput(namespace, "list", {"items": [1]}, index=False)
        root_items = await store.asearch((owner, str(runtime_target.runtime_id)))
        assert len(root_items) == 1 and root_items[0].value == {"items": [1]}
        assert not await store.asearch((owner, str(runtime_target.id)))
        for item in root_items:
            await store.adelete(item.namespace, item.key)
        assert await store.aget(namespace, "list") is None
    finally:
        await store.adelete(namespace, "list")
        await store.aclose()


async def test_declared_voice_context_is_owner_fenced_and_arbitrary_threads_are_refused(
    native_connection: AsyncConnection[DictRow],
    runtime_target: ConversationRef,
    async_engine: AsyncEngine,
) -> None:
    """Direct voice has no conversation checkpoint, but never outlives its account."""
    store = RuntimeAsyncPostgresStore(native_connection)
    owner = str(runtime_target.owner_id)
    scope = voice_context_id("live_session", str(uuid4()))
    namespace = (owner, scope, "context", "event")
    try:
        for invalid in (
            "unregistered-child",
            "live_session:invalid",
            "other_surface:" + str(uuid4()),
        ):
            with pytest.raises(ValueError):
                await store.aput((owner, invalid, "context", "event"), "list", {}, index=False)
        await store.aput(namespace, "list", {"items": [1]}, index=False)
        async with AsyncSession(async_engine) as db:
            await db.execute(
                update(User).where(User.id == runtime_target.owner_id).values(is_active=False)
            )
            await db.commit()
        await store.adelete(namespace, "list")
        with pytest.raises(RuntimeError, match="runtime"):
            await store.aput(namespace, "list", {"items": [2]}, index=False)
        assert await store.aget(namespace, "list") is None
    finally:
        await store.adelete(namespace, "list")
        await store.aclose()

"""Runtime writes use a SQL fence; account semantic memory keeps its native path."""

import asyncio
from collections.abc import Callable, Iterable
from uuid import UUID

import orjson
from langchain_core.embeddings import Embeddings
from langgraph.checkpoint.postgres import _ainternal
from langgraph.store.base import BaseStore, Op, PutOp, Result, SearchOp, TTLConfig
from langgraph.store.postgres import AsyncPostgresStore
from langgraph.store.postgres.base import PostgresIndexConfig
from psycopg import AsyncPipeline

from src.core.tool_context_scope import is_voice_context_id
from src.domains.conversations.runtime_persistence import (
    borrow_native_connection,
    owner_write_connection,
    runtime_write_connection,
)
from src.infrastructure.async_utils import cancel_and_join


async def close_native_store(store: AsyncPostgresStore) -> None:
    """Join the native TTL and batching tasks on their owning event loop."""
    store._ttl_stop_event.set()
    await _cancel_and_join_tasks(
        [task for task in (store._ttl_sweeper_task, store._task) if task is not None]
    )


async def _cancel_and_join_tasks(tasks: Iterable[asyncio.Task[object]]) -> None:
    """A failed closer cannot prevent its siblings from releasing their resources."""
    owned = tuple(dict.fromkeys(tasks))
    for task in owned:
        task.cancel()
    cancelled = False
    failures: list[Exception] = []
    for task in owned:
        try:
            await cancel_and_join(task)
        except asyncio.CancelledError:
            cancelled = True
        except Exception as exc:
            failures.append(exc)
    if failures:
        raise ExceptionGroup("Runtime Store shutdown failed", failures)
    if cancelled:
        raise asyncio.CancelledError


class RuntimeAsyncPostgresStore(AsyncPostgresStore):
    """A pooled Store whose runtime mutations cannot resurrect a retired context.

    BaseStore's native async convenience methods call abatch directly. Avoid
    coalescing unrelated callers in the vendor queue: a stale runtime refusal
    must not fail another person's otherwise successful memory write. Explicit
    abatch callers retain their result ordering and native read-before-put rule.
    The vendor's eagerly allocated idle batching task is still joined at close.
    """

    aget = BaseStore.aget
    aput = BaseStore.aput
    adelete = BaseStore.adelete
    asearch = BaseStore.asearch
    alist_namespaces = BaseStore.alist_namespaces

    def __init__(
        self,
        conn: _ainternal.Conn,
        *,
        pipe: AsyncPipeline | None = None,
        deserializer: Callable[[bytes | orjson.Fragment], dict[str, object]] | None = None,
        index: PostgresIndexConfig | None = None,
        ttl: TTLConfig | None = None,
    ) -> None:
        self._closed = False
        self._active_batches: set[asyncio.Task[object]] = set()
        super().__init__(conn, pipe=pipe, deserializer=deserializer, index=index, ttl=ttl)

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        """Leave global embeddings outside every runtime transaction."""
        if self._closed:
            raise RuntimeError("Runtime Store is closed")
        current = asyncio.current_task()
        assert current is not None
        self._active_batches.add(current)
        try:
            operations = list(ops)
            runtime_ops, ordinary = _partition_batch(operations)
            results: list[Result] = [None] * len(operations)
            if ordinary:
                values = await self._ordinary_batch([op for _, op in ordinary])
                for (index, _), value in zip(ordinary, values, strict=True):
                    results[index] = value
            for op in runtime_ops:
                await self._put_runtime(op)
            return results
        finally:
            self._active_batches.discard(current)

    async def _ordinary_batch(self, operations: list[Op]) -> list[Result]:
        """Compute native embedding requests BEFORE checking out a connection.

        The native SQL builders own field selection and deduplication. Their
        SQL is never copied or executed here. The native executor receives an
        operation-local embedding snapshot that can perform no network I/O.
        """
        if self.embeddings is None or self.index_config is None:
            return await super().abatch(operations)
        _, search_requests = self._prepare_batch_search_queries(
            [(i, op) for i, op in enumerate(operations) if isinstance(op, SearchOp)]
        )
        _, put_request = self._prepare_batch_PUT_queries(
            [(i, op) for i, op in enumerate(operations) if isinstance(op, PutOp)]
        )
        groups = [
            [text for _, text in search_requests],
            [text for _, _, _, text in put_request[1]] if put_request else [],
        ]
        vectors: dict[str, list[float]] = {}
        for texts in groups:
            if texts:
                embedded = await self.embeddings.aembed_documents(texts)
                vectors.update(zip(texts, embedded, strict=True))
        if not vectors:
            return await super().abatch(operations)
        index: PostgresIndexConfig = {**self.index_config, "embed": _PreparedEmbeddings(vectors)}
        async with borrow_native_connection(self.conn, self.lock) as connection:
            native = AsyncPostgresStore(
                connection, index=index, ttl=self.ttl_config, deserializer=self._deserializer
            )
            try:
                return await native.abatch(operations)
            finally:
                await close_native_store(native)

    async def _put_runtime(self, op: PutOp) -> None:
        """Use a non-semantic native delegate on the fence's exact connection."""
        owner_id = UUID(op.namespace[0])
        scope = op.namespace[1]
        fence = (
            owner_write_connection(self.conn, self.lock, owner_id=owner_id)
            if is_voice_context_id(scope)
            else runtime_write_connection(
                self.conn, self.lock, owner_id=owner_id, runtime_id=UUID(scope)
            )
        )
        async with fence as connection:
            native = AsyncPostgresStore(connection)
            try:
                await native.abatch([op])
            finally:
                await close_native_store(native)

    async def aclose(self) -> None:
        """Stop accepting work, drain owned operations, then join vendor tasks."""
        self._closed = True
        current = asyncio.current_task()
        active = tuple(task for task in self._active_batches if task is not current)
        try:
            await _cancel_and_join_tasks(active)
        finally:
            await close_native_store(self)


def _is_runtime(op: PutOp) -> bool:
    """Both legacy and current context shapes belong to this guarded family."""
    namespace = op.namespace
    return (len(namespace) > 2 and namespace[2] == "context") or (
        len(namespace) > 1 and namespace[1] == "context"
    )


def _partition_batch(operations: list[Op]) -> tuple[list[PutOp], list[tuple[int, Op]]]:
    """Retain native last-write-wins and original result positions across scopes."""
    last_put = {
        (op.namespace, op.key): index
        for index, op in enumerate(operations)
        if isinstance(op, PutOp)
    }
    runtime_ops: list[PutOp] = []
    ordinary: list[tuple[int, Op]] = []
    for index, op in enumerate(operations):
        if isinstance(op, PutOp) and last_put[(op.namespace, op.key)] != index:
            continue
        if isinstance(op, PutOp) and op.value is not None and _is_runtime(op):
            _validate_runtime_put(op)
            runtime_ops.append(op)
        else:
            ordinary.append((index, op))
    return runtime_ops, ordinary


def _validate_runtime_put(op: PutOp) -> None:
    """Refuse ambiguous scopes and semantic work before opening a transaction."""
    if len(op.namespace) not in (4, 5) or op.namespace[2] != "context":
        raise ValueError("Invalid tool context runtime identity")
    UUID(op.namespace[0])
    if not is_voice_context_id(op.namespace[1]):
        UUID(op.namespace[1])
    if op.index is not False:
        raise ValueError("Runtime tool contexts require index=False")


class _PreparedEmbeddings(Embeddings):
    """An operation's exact vectors, with no provider or fallback under SQL."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return only vectors prepared by the native request builders."""
        return [self._vectors[text] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Refuse an unprepared request instead of making remote I/O under SQL."""
        return self._vectors[text]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """No executor or network is needed to read an operation-local snapshot."""
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Read a single prepared query without allocating an executor."""
        return self.embed_query(text)

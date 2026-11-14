"""Native checkpoint semantics with a transaction-bound conversation write fence."""

from collections.abc import Sequence

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from src.domains.conversations.runtime_identity import (
    checkpoint_execution,
    checkpoint_identity,
    retain_checkpoint_identity,
)
from src.domains.conversations.runtime_persistence import runtime_write_connection


class RuntimeAsyncPostgresSaver(AsyncPostgresSaver):
    """Keep native SQL/serialization and add only the authority to write it.

    No per-request connection is assigned to the singleton. The short-lived
    delegate owns no pool/task and uses the exact serializer of this adapter.
    Native synchronous methods dispatch through these asynchronous overrides.
    """

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Commit all checkpoint rows/blobs while the runtime remains current."""
        identity = checkpoint_identity(config)
        async with runtime_write_connection(
            self.conn,
            self.lock,
            owner_id=identity.owner_id,
            runtime_id=identity.runtime_id,
            identity=identity,
            execution=checkpoint_execution(config),
        ) as connection:
            native = AsyncPostgresSaver(connection, serde=self.serde)
            result = await native.aput(config, checkpoint, metadata, new_versions)
        return retain_checkpoint_identity(config, result)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, object]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Fence pending task writes as well as completed checkpoints."""
        identity = checkpoint_identity(config)
        async with runtime_write_connection(
            self.conn,
            self.lock,
            owner_id=identity.owner_id,
            runtime_id=identity.runtime_id,
            identity=identity,
            execution=checkpoint_execution(config),
        ) as connection:
            native = AsyncPostgresSaver(connection, serde=self.serde)
            await native.aput_writes(config, writes, task_id, task_path)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Restore checkpoint coordinates without losing the caller's identity."""
        result = await super().aget_tuple(config)
        if result is None:
            return None
        return result._replace(
            config=retain_checkpoint_identity(config, result.config),
            parent_config=(
                retain_checkpoint_identity(config, result.parent_config)
                if result.parent_config is not None
                else None
            ),
        )

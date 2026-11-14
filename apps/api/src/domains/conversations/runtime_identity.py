"""Explicit business and checkpoint identities; a runtime is never a foreign key."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from src.core.conversation_execution import ExecutionIdentity, ExecutionRevoked
from src.core.conversation_target import ConversationRef
from src.core.field_names import (
    FIELD_ACTIVITY_ID,
    FIELD_CONVERSATION_ID,
    FIELD_CONVERSATION_REVISION,
    FIELD_EXECUTION_SCOPE,
    FIELD_FENCE,
    FIELD_OWNER_TOKEN,
    FIELD_RUNTIME_ID,
    FIELD_RUNTIME_SCOPE,
    FIELD_USER_ID,
    FIELD_WORKER_ID,
)
from src.core.run_authority import current_run_authority


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    """The immutable scope every conversation checkpoint writer must supply."""

    owner_id: UUID
    conversation_id: UUID
    revision: int
    runtime_id: UUID


def checkpoint_config(target: ConversationRef) -> RunnableConfig:
    """Project a resolved target into LangGraph's transport configuration."""
    config: RunnableConfig = {
        "configurable": {
            "thread_id": str(target.runtime_id),
            "checkpoint_ns": "",
            FIELD_RUNTIME_SCOPE: {
                FIELD_USER_ID: str(target.owner_id),
                FIELD_CONVERSATION_ID: str(target.id),
                FIELD_CONVERSATION_REVISION: target.revision,
                FIELD_RUNTIME_ID: str(target.runtime_id),
            },
        }
    }
    authority = current_run_authority()
    if authority is not None and authority.admission.target == target:
        authority.require_current()
        identity = authority.admission.identity
        config["configurable"][FIELD_EXECUTION_SCOPE] = {
            FIELD_ACTIVITY_ID: str(identity.activity_id),
            FIELD_WORKER_ID: str(identity.worker_id),
            FIELD_OWNER_TOKEN: str(identity.owner_token),
            FIELD_FENCE: identity.fence,
        }
    return config


def checkpoint_execution(config: RunnableConfig) -> ExecutionIdentity:
    """Read a private invocation identity; a read-only config authorizes no write."""
    values = config.get("configurable", {}).get(FIELD_EXECUTION_SCOPE)
    if not isinstance(values, Mapping):
        raise ExecutionRevoked()
    fence = values.get(FIELD_FENCE)
    if type(fence) is not int or fence <= 0:
        raise ExecutionRevoked()
    try:
        return ExecutionIdentity(
            activity_id=_uuid(values.get(FIELD_ACTIVITY_ID)),
            worker_id=_uuid(values.get(FIELD_WORKER_ID)),
            owner_token=_uuid(values.get(FIELD_OWNER_TOKEN)),
            fence=fence,
        )
    except (ValueError, TypeError) as exc:
        raise ExecutionRevoked() from exc


def checkpoint_identity(config: RunnableConfig) -> RuntimeIdentity:
    """Refuse an incomplete or synthetic write scope before opening a transaction.

    Native subgraphs share their parent's thread and use checkpoint_ns. LIA's
    synthetic ReAct sub-runs have no checkpointer; allowing an arbitrary child
    thread here would create storage outside the runtime's cleanup inventory.
    """
    identity = runtime_identity(config)
    if identity is None:
        raise ValueError("Unregistered checkpoint runtime identity")
    try:
        thread_id = _uuid(config.get("configurable", {}).get("thread_id"))
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid checkpoint thread identity") from exc
    if thread_id != identity.runtime_id:
        raise ValueError("Unregistered checkpoint runtime identity")
    return identity


def runtime_identity(config: RunnableConfig) -> RuntimeIdentity | None:
    """Read declared runtime ancestry, including on an uncheckpointed child.

    This is persistence plumbing, not a second source of user preferences or
    tool dependencies. Ordinary nodes continue to read LiaRuntimeContext.
    """
    values = config.get("configurable", {}).get(FIELD_RUNTIME_SCOPE)
    if values is None:
        return None
    if not isinstance(values, Mapping):
        raise ValueError("Invalid conversation runtime identity")
    revision = values.get(FIELD_CONVERSATION_REVISION)
    if type(revision) is not int or revision < 0:
        raise ValueError("Invalid conversation runtime identity")
    try:
        identity = RuntimeIdentity(
            owner_id=_uuid(values.get(FIELD_USER_ID)),
            conversation_id=_uuid(values.get(FIELD_CONVERSATION_ID)),
            revision=revision,
            runtime_id=_uuid(values.get(FIELD_RUNTIME_ID)),
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid conversation runtime identity") from exc
    return identity


def _uuid(value: object) -> UUID:
    """Read the exact supported wire types, never stringify arbitrary objects."""
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise TypeError("Expected a UUID identity")


def retain_checkpoint_identity(original: RunnableConfig, saved: RunnableConfig) -> RunnableConfig:
    """Keep our identity when the native saver returns only checkpoint coordinates."""
    source = original.get("configurable", {})
    return {
        **saved,
        "configurable": {
            **{
                key: value
                for key, value in saved.get("configurable", {}).items()
                if key not in (FIELD_RUNTIME_SCOPE, FIELD_EXECUTION_SCOPE)
            },
            **{
                key: source[key]
                for key in (FIELD_RUNTIME_SCOPE, FIELD_EXECUTION_SCOPE)
                if key in source
            },
        },
    }

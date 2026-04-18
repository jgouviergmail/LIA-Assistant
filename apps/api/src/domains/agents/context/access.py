"""TCM access helper — centralises manager + store acquisition from a config.

Encapsulates the recurring pattern needed by any side-effect that mutates the
Tool Context Manager from a graph node / service:

    1. Acquire the async store singleton (shared instance).
    2. Extract user_id and thread_id from the RunnableConfig.
    3. Instantiate the manager.
    4. Skip gracefully when any of the above is missing — side-effects must
       NEVER raise in the response path.

Use `get_tcm_session(config)` to get a ready-to-use `TcmSession` bundle, or
None when the session cannot be built (missing config, no store).

Typical caller shape:

    session = await get_tcm_session(config)
    if not session:
        return
    await session.manager.set_current_item(
        user_id=session.user_id,
        session_id=session.session_id,
        domain="events",
        item=item,
        set_by="auto",
        turn_id=turn_id,
        store=session.store,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableConfig

from src.core.field_names import FIELD_THREAD_ID, FIELD_USER_ID
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore

    from src.domains.agents.context.manager import ToolContextManager

logger = get_logger(__name__)


@dataclass(frozen=True)
class TcmSession:
    """Ready-to-use TCM handle for the current user+thread.

    Attributes:
        manager: Instance of ToolContextManager.
        store: LangGraph BaseStore singleton for persistence.
        user_id: Stringified user identifier.
        session_id: LangGraph thread_id (conversation scope).
    """

    manager: ToolContextManager
    store: BaseStore
    user_id: str
    session_id: str


async def get_tcm_session(config: RunnableConfig) -> TcmSession | None:
    """Build a TcmSession from a RunnableConfig.

    Encapsulates the recurring acquisition pattern for TCM side-effects:
    fetch the shared store, extract user_id/thread_id from config.configurable,
    instantiate the manager. Returns None (never raises) when any required
    piece is missing — callers treat None as "skip this side-effect silently".

    Args:
        config: RunnableConfig with user_id and thread_id in configurable.

    Returns:
        Ready-to-use TcmSession bundle, or None when the session cannot be
        built (missing store, missing user_id, missing thread_id).
    """
    try:
        from src.domains.agents.context.manager import ToolContextManager
        from src.domains.agents.context.store import get_tool_context_store

        store = await get_tool_context_store()
        if not store:
            return None

        configurable = config.get("configurable", {}) if config else {}
        user_id = configurable.get(FIELD_USER_ID)
        session_id = configurable.get(FIELD_THREAD_ID)
        if not user_id or not session_id:
            return None

        return TcmSession(
            manager=ToolContextManager(),
            store=store,
            user_id=str(user_id),
            session_id=str(session_id),
        )
    except Exception:
        # Defensive: never let TCM acquisition break the caller's control flow.
        logger.exception("tcm_session_acquisition_failed")
        return None


__all__ = ["TcmSession", "get_tcm_session"]

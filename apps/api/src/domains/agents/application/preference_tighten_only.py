"""The chat may switch the account's MCP strategy on, never off (spec 2026-10-30 D7).

« Always ask before an MCP tool » travels in the preferences patch; the schema publishes
``true`` alone (``PREFERENCE_TIGHTEN_ONLY``). The judge installed with the person's MCP
servers refuses any other value and judges « always » by the computation that alerts the
person on the settings page — at proposal and again at the write, against the state the
write replaces. A deployment without personal MCP servers has no judge, and nothing
unjudged goes through.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.preference_fields import PreferenceField
from src.domains.agents.application.schemas import PreferencePatch
from src.infrastructure.mcp.personal_state_gateway import get_personal_mcp_state


async def refuse_strategy_loosening(
    db: AsyncSession, actor_id: UUID, patch: PreferencePatch
) -> None:
    """Judge a preferences patch that carries the account's MCP strategy.

    Args:
        db: The session the proposal or the write runs in.
        actor_id: The person.
        patch: The validated preferences patch.

    Raises:
        ConfirmationLooseningRefused: A value but « always », or one that would make LIA
            ask less on one of the person's servers.
        AuthorizationError: No judge is installed (``SERVICE_UNAVAILABLE``).
    """
    if PreferenceField.MCP_CONFIRMATION.value not in patch.model_fields_set:
        return
    judge = get_personal_mcp_state().judge_strategy
    if judge is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    await judge(db, actor_id, patch.mcp_hitl_required)

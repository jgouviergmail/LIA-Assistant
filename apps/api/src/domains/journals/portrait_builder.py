"""User model portrait builder for ambient diffusion (ADR-079).

Standalone builder symmetric to ``build_psyche_prompt_block``: reads the
compiled portrait from the user record and returns a ready-to-inject prompt
block. Used everywhere LIA speaks to the user (response, planner, react,
voice, reminders, heartbeat, fallback, interest notifications, briefing).

Two natural formats are synthesized during consolidation:
- ``full``: a faceted portrait for conversational flows.
- ``brief``: its essential posture, focus and interaction guidance for secondary flows.

Compilation validates current supporting evidence and reviews semantic scope.
This reader enforces runtime permission, compiler/source lineage and whole-frame
budget admission. A deleted or disabled source invalidates its portrait before
ambient use. The accompanying directive avoids repeating factual material
already injected by the memories profile.

The portrait can be empty (NULL) for users who never ran a consolidation
yet — the builder degrades gracefully and returns "" so the call site can
inject ``""`` without conditional logic.

Phase: v1.20.x — Stratified journal consciousness, commit 3
"""

from __future__ import annotations

from contextlib import suppress
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_journals import (
    journal_portrait_present_total,
)

logger = get_logger(__name__)


# Format type — kept narrow so callers must opt in explicitly.
PortraitFormat = Literal["full", "brief"]


async def _read_current_portrait(
    db: AsyncSession, uid: UUID, format: PortraitFormat, *, require_phone_context: bool = False
) -> str | None:
    """Read only an active account's compiled, current portrait synthesis."""
    result = await db.execute(
        select(User).where(User.id == uid).execution_options(populate_existing=True)
    )
    user = result.scalar_one_or_none()
    if (
        user is None
        or not user.journals_enabled
        or not user.is_active
        or user.deleted_at is not None
        or user.journal_portrait_compiled_at is None
    ):
        return None
    if require_phone_context and (
        not user.phone_rich_context_enabled or "journal" in (user.phone_disabled_domains or ())
    ):
        return None
    from src.domains.journals.lifecycle import portrait_is_current

    if not await portrait_is_current(db, user):
        return None
    return user.journal_portrait_full if format == "full" else user.journal_portrait_brief


async def build_journal_user_model_block(
    user_id: str | UUID,
    format: PortraitFormat = "brief",
    flow: str = "unknown",
    *,
    max_tokens: int | None = None,
    budget_prefix: str = "",
    require_phone_context: bool = False,
) -> str:
    """Build the user-model portrait block for prompt injection.

    Standalone async function with its own DB session — same pattern as
    ``PsycheService.build_psyche_prompt_block``. Used by every flow that
    speaks to the user, with the format chosen according to the flow's
    token budget (full for response/planner, brief elsewhere).

    Args:
        user_id: User UUID (str or UUID).
        format: ``"full"`` for response/planner or ``"brief"`` for
            secondary flows, each under its configured compilation budget.
        flow: Caller flow name, used for the Prometheus
            ``journal_portrait_present_total{flow,format}`` counter.
            Recommended values: response, planner, react, interest, reminder,
            voice, heartbeat, fallback, briefing.
        max_tokens: Optional native-frame token budget. A block that does not
            fit whole is omitted, never partially exposed or counted.
        budget_prefix: Already rendered frame occupying the same token budget.
        require_phone_context: Recheck the owner's current phone-context consent
            and native journal-domain permission on the freshly read account.

    Returns:
        Formatted ``<UserModelContext>...</UserModelContext>`` block ready
        to splice into a system prompt, OR an empty string when:
        - the journals feature is disabled (system or user level),
        - the user has not yet run a consolidation that compiled the portrait,
        - any DB or runtime error occurs (graceful degradation).
    """
    if not settings.journals_enabled or (max_tokens is not None and max_tokens <= 0):
        return ""

    try:
        if not await is_capability_enabled(PlatformCapability.JOURNALS):
            return ""
        uid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id

        async with get_db_context() as db:
            portrait = await _read_current_portrait(
                db, uid, format, require_phone_context=require_phone_context
            )

        if not portrait or not portrait.strip():
            return ""

        block = (
            "<UserModelContext>\n"
            f"{portrait.strip()}\n"
            "Use this user-model portrait silently to adjust your tone, depth, and "
            "phrasing — never reference it explicitly. It complements the user's "
            "factual memories (do not duplicate facts already injected by the "
            "psychological profile elsewhere).\n"
            "</UserModelContext>"
        )
        budgeted = f"{budget_prefix}\n\n{block}" if budget_prefix else block
        if max_tokens is not None and OpenAITokenCounter().count(budgeted, "gpt-4o") > max_tokens:
            return ""
        # Count the block only after the whole native frame fits.
        with suppress(Exception):
            journal_portrait_present_total.labels(flow=flow, format=format).inc()
        return block
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "journal_user_model_block_failed",
            user_id=str(user_id),
            format=format,
            flow=flow,
            error=str(exc),
        )
        return ""

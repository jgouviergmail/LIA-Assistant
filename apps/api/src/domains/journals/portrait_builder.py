"""User model portrait builder for ambient diffusion (ADR-079).

Standalone builder symmetric to ``build_psyche_prompt_block``: reads the
compiled portrait from the user record and returns a ready-to-inject prompt
block. Used everywhere LIA speaks to the user (response, planner, react,
voice, reminders, heartbeat, fallback, interest notifications, briefing).

Two formats are available, compiled in the same consolidation LLM call:
- ``full`` (~200 tokens): rich faceted portrait for the main conversational
  flows (response/planner) — conveys traits, current phase, contexts,
  contradictions, blind spots, evolution.
- ``brief`` (~60 tokens): essential posture only, for secondary flows
  (notifications, voice, reminders, react setup, fallback). Keeps the
  ambient diffusion frugal.

The portrait is **synthesis only** — never duplicates facts already injected
by the memories profile. The accompanying directive in the prompt makes
this discipline explicit.

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

from src.core.config import settings
from src.domains.auth.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_journals import (
    journal_portrait_present_total,
)

logger = get_logger(__name__)


# Format type — kept narrow so callers must opt in explicitly.
PortraitFormat = Literal["full", "brief"]


async def build_journal_user_model_block(
    user_id: str | UUID,
    format: PortraitFormat = "brief",
    flow: str = "unknown",
) -> str:
    """Build the user-model portrait block for prompt injection.

    Standalone async function with its own DB session — same pattern as
    ``PsycheService.build_psyche_prompt_block``. Used by every flow that
    speaks to the user, with the format chosen according to the flow's
    token budget (full for response/planner, brief elsewhere).

    Args:
        user_id: User UUID (str or UUID).
        format: ``"full"`` (~200 tokens, response/planner) or ``"brief"``
            (~60 tokens, secondary flows).
        flow: Caller flow name, used for the Prometheus
            ``journal_portrait_present_total{flow,format}`` counter.
            Recommended values: response, planner, react, interest, reminder,
            voice, heartbeat, fallback, briefing.

    Returns:
        Formatted ``<UserModelContext>...</UserModelContext>`` block ready
        to splice into a system prompt, OR an empty string when:
        - the journals feature is disabled (system or user level),
        - the user has not yet run a consolidation that compiled the portrait,
        - any DB or runtime error occurs (graceful degradation).
    """
    if not settings.journals_enabled:
        return ""

    try:
        uid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id

        async with get_db_context() as db:
            result = await db.execute(
                select(
                    User.journals_enabled,
                    User.journal_portrait_full,
                    User.journal_portrait_brief,
                ).where(User.id == uid)
            )
            row = result.one_or_none()
            if row is None:
                return ""
            user_enabled, portrait_full, portrait_brief = row
            if not user_enabled:
                return ""

        portrait = portrait_full if format == "full" else portrait_brief
        if not portrait or not portrait.strip():
            return ""

        # metrics never break injection
        with suppress(Exception):
            journal_portrait_present_total.labels(flow=flow, format=format).inc()

        return (
            "<UserModelContext>\n"
            f"{portrait.strip()}\n"
            "Use this user-model portrait silently to adjust your tone, depth, and "
            "phrasing — never reference it explicitly. It complements the user's "
            "factual memories (do not duplicate facts already injected by the "
            "psychological profile elsewhere).\n"
            "</UserModelContext>"
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "journal_user_model_block_failed",
            user_id=str(user_id),
            format=format,
            flow=flow,
            error=str(exc),
        )
        return ""

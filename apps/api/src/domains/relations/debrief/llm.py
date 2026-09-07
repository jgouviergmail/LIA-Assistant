"""Writing one relationship debrief — a single structured call.

One LLM slot (``relation_debrief``), one versioned prompt, one structured
answer. The evidence is already bounded by the reader's own scope
(``max_items`` per section), so this is a small call over a small payload.

Token usage goes through ``track_proactive_tokens`` like every other non-chat
call in this codebase: the debrief appears in ``token_usage_logs`` and the
user's statistics, never in a parallel accounting nobody would think to open.

The prompt carries no number in prose (ADR-184): the list bounds this module
enforces are the ones it interpolates, so what the schema will trim is what the
writer could read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.core.config import settings as app_settings
from src.core.constants import (
    RELATION_DEBRIEF_LLM_TYPE,
    RELATION_DEBRIEF_MAX_NOTABLE_FACTS_DEFAULT,
    RELATION_DEBRIEF_MAX_OPEN_POINTS_DEFAULT,
    RELATION_DEBRIEF_PROMPT_NAME,
)
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.llm_usage import LLMUsage
from src.core.user_display import resolve_user_display_name
from src.domains.relations.debrief.prompts import load_debrief_prompt
from src.domains.relations.debrief.schemas import DebriefBody, DebriefDraft
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output_with_retry
from src.infrastructure.llm.token_capture import TokenCaptureHandler

if TYPE_CHECKING:
    from datetime import date

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DebriefAuthor:
    """Who the debrief is written FOR — the four fields the prompt needs.

    A snapshot rather than the ORM ``User``: the build spans an LLM round-trip,
    and carrying a detached instance across it means any attribute a future
    version touches becomes a lazy load on a closed session. Four plain values
    cannot do that, and they state exactly what this module depends on.
    """

    user_id: UUID
    full_name: str | None
    email: str | None
    journals_enabled: bool


async def _personality_brief(user_id: Any) -> str:
    """The user's personality instruction, best-effort.

    Same treatment as the briefing: the debrief should sound like LIA, and a
    personality that cannot be read is a missing flavour, never a failed build.
    """
    try:
        from src.domains.personalities.service import PersonalityService
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            return await PersonalityService(db).get_prompt_instruction_for_user(user_id) or ""
    except Exception as exc:  # noqa: BLE001 — flavour, never a blocker
        logger.warning("relation_debrief_personality_failed", error_type=type(exc).__name__)
        return ""


async def _user_model_block(author: DebriefAuthor) -> str:
    """The compiled journal portrait, best-effort and gated by its own flag."""
    if not author.journals_enabled:
        return ""
    try:
        from src.domains.journals.portrait_builder import build_journal_user_model_block

        return await build_journal_user_model_block(
            user_id=str(author.user_id), format="brief", flow="relation_debrief"
        )
    except Exception as exc:  # noqa: BLE001 — a bonus, never a blocker
        logger.warning("relation_debrief_portrait_failed", error_type=type(exc).__name__)
        return ""


async def write_debrief(
    *,
    author: DebriefAuthor,
    person_name: str,
    evidence: dict[str, Any],
    language: str,
    local_date: date,
) -> tuple[DebriefBody, LLMUsage]:
    """Write one relationship's debrief from the evidence it was given.

    Args:
        author: The reader — the debrief is written FOR them, about the person.
        person_name: The relationship, as the CRM displays it.
        evidence: The 360° payload, already scoped and already honest about
            what it could not read.
        language: Backend-canonical language to write in.
        local_date: The reader's local date, so "recently" means something.

    Returns:
        The synthesis and what it cost.

    Raises:
        StructuredOutputError: When the model never produced a valid answer.
    """
    config = get_llm_config_for_agent(app_settings, RELATION_DEBRIEF_LLM_TYPE)
    capture = TokenCaptureHandler()
    system = load_debrief_prompt(RELATION_DEBRIEF_PROMPT_NAME).format(
        user_name=resolve_user_display_name(author.full_name, author.email, fallback="there"),
        language=language,
        personality_brief=await _personality_brief(author.user_id),
        user_model_block=await _user_model_block(author),
        person_name=person_name,
        today_iso=local_date.isoformat(),
        # Compact JSON, like the planner catalogue: lossless, and it preserves
        # the distinction the whole design rests on — an ABSENT key was never
        # read, an empty list was read and found nothing.
        evidence=json.dumps(evidence, separators=(",", ":"), ensure_ascii=False, default=str),
        max_open_points=RELATION_DEBRIEF_MAX_OPEN_POINTS_DEFAULT,
        max_notable_facts=RELATION_DEBRIEF_MAX_NOTABLE_FACTS_DEFAULT,
    )
    draft = await get_structured_output_with_retry(
        get_llm(RELATION_DEBRIEF_LLM_TYPE),
        [SystemMessage(content=system), HumanMessage(content=person_name)],
        DebriefDraft,
        provider=str(config.provider),
        node_name=RELATION_DEBRIEF_LLM_TYPE,
        config=RunnableConfig(callbacks=[capture]),
        # Named so the account's ceiling applies: this door carried no usage
        # check at all until 2026-09-07.
        user_id=author.user_id,
    )
    # No PII at INFO: that a debrief was written and what it cost, never who
    # it is about nor a line of what it says.
    logger.info(
        "relation_debrief_written",
        user_id=str(author.user_id),
        tokens_in=capture.tokens_in,
        tokens_out=capture.tokens_out,
    )
    # Repaired here, never refused above: a model one point over the published
    # bound must not cost the reader their debrief.
    return draft.to_body(), _usage_of(capture, str(config.model))


def _usage_of(capture: TokenCaptureHandler, model_name: str) -> LLMUsage:
    """What this call consumed, priced — a DISPLAY summary, never an account.

    The pricing lookup is best-effort on purpose: a cache that cannot price a
    model must not cost the reader their debrief, and the authoritative record
    of the spend is written separately into ``token_usage_logs``.

    Args:
        capture: The token counters this call accumulated.
        model_name: The model the slot resolved to.

    Returns:
        The usage summary stored beside the words and shown under them.
    """
    cost_eur = 0.0
    try:
        _cost_usd, cost_eur = get_cached_cost_usd_eur(
            model=model_name,
            prompt_tokens=capture.tokens_in,
            completion_tokens=capture.tokens_out,
            cached_tokens=capture.tokens_cache,
        )
    except Exception as exc:  # noqa: BLE001 — a price is a nicety, never a blocker
        logger.warning("relation_debrief_pricing_failed", error_type=type(exc).__name__)
    return LLMUsage(
        tokens_in=capture.tokens_in,
        tokens_out=capture.tokens_out,
        tokens_cache=capture.tokens_cache,
        cost_eur=cost_eur,
        model_name=model_name,
    )

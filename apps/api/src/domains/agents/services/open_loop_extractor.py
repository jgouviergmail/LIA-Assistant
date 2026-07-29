"""Open-loop extraction from conversation turns (P5, ADR-139).

Fifth post-response background extraction (pattern: ``memory_extractor``).
One structured LLM pass sees the conversation tail AND the user's current
OPEN loops, and emits:

- ``open`` items — new commitments to track ("je dois rappeler le plombier",
  "Marie doit m'envoyer le devis");
- ``close`` items — conversational closure of an existing loop ("c'est fait,
  j'ai rappelé le plombier") targeting a loop id from the provided list.

Application rules are deterministic and testable in isolation
(:func:`apply_extraction`): per-user OPEN cap, per-turn item cap, duplicate
subjects skipped, tolerant ISO parsing of the advisory ``due_hint``.

Fire-and-forget contract: :func:`extract_open_loops_background` never raises.
"""

from __future__ import annotations

import time as _time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field

from src.core.config import settings
from src.infrastructure.llm.token_capture import TokenCaptureHandler

if TYPE_CHECKING:
    from src.domains.open_loops.repository import OpenLoopRepository

logger = structlog.get_logger(__name__)

# Conversation tail passed to the extraction LLM (turns, not tokens — the
# extraction targets the LAST exchange; older loops are already tracked).
_EXTRACTION_MESSAGE_TAIL = 6
# Truncation per message (token budget guard, mirrors memory extraction).
_EXTRACTION_MESSAGE_MAX_CHARS = 500

# ---------------------------------------------------------------------------
# Debug-panel cache (pop-once per run_id — same pattern and rationale as
# journals/extraction_service: the SSE generator pops the result after
# await_run_id_tasks and emits it as a debug_metrics_update chunk; TTL
# eviction bounds growth when a result is never consumed).
# ---------------------------------------------------------------------------

_EXTRACTION_DEBUG_TTL_SECONDS: int = 300

_extraction_debug_results: dict[str, tuple[float, dict[str, Any]]] = {}


def _evict_stale_debug_entries() -> None:
    """Drop entries older than the TTL — called on BOTH store and pop.

    Store-side eviction matters: when no client ever enables the debug
    panel, nothing pops, and pop-only eviction would let the cache grow
    for the whole process lifetime (one entry per turn).
    """
    now = _time.monotonic()
    stale = [
        k
        for k, (ts, _) in _extraction_debug_results.items()
        if now - ts > _EXTRACTION_DEBUG_TTL_SECONDS
    ]
    for k in stale:
        del _extraction_debug_results[k]


def _store_extraction_debug(run_id: str, data: dict[str, Any]) -> None:
    """Store the extraction outcome for the debug panel, keyed by run_id."""
    _evict_stale_debug_entries()
    _extraction_debug_results[run_id] = (_time.monotonic(), data)


def pop_extraction_debug(run_id: str) -> dict[str, Any] | None:
    """Pop the extraction debug payload for a run (evicts stale entries).

    Returns:
        {items_parsed, opened, closed, skipped, items} or None.
    """
    _evict_stale_debug_entries()
    entry = _extraction_debug_results.pop(run_id, None)
    return entry[1] if entry is not None else None


class OpenLoopItem(BaseModel):
    """One extracted action: open a new loop or close an existing one."""

    model_config = ConfigDict(extra="ignore")

    action: Literal["open", "close"] = Field(description="open a new loop or close one")
    subject: str = Field(description="What the commitment is about, user's language")
    counterparty: str | None = Field(
        default=None, description="Person/organization on the other side, if named"
    )
    direction: Literal["user_owes", "waiting_on_other"] = Field(
        default="user_owes",
        description="user_owes = the user committed; waiting_on_other = user waits",
    )
    due_hint_iso: str | None = Field(
        default=None,
        description="ISO-8601 deadline if the conversation names one, else null",
    )
    loop_id: str | None = Field(
        default=None,
        description="EXACT id from CURRENT OPEN LOOPS — required for action=close",
    )


class OpenLoopExtraction(BaseModel):
    """Structured output of the extraction LLM call."""

    model_config = ConfigDict(extra="ignore")

    items: list[OpenLoopItem] = Field(default_factory=list)


def _parse_due_hint(raw: str | None) -> datetime | None:
    """Parse the advisory ISO deadline, tolerantly (LLM-shaped input).

    An offset-less ISO string (frequent LLM output) is coerced to UTC: the
    column is timestamptz and the codebase invariant is aware-UTC. The hint
    is advisory (nudge timing at a 48 h scale), so the ≤ few-hours offset
    ambiguity of that coercion is acceptable by design.
    """
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _format_messages_tail(messages: list[BaseMessage]) -> str:
    """Render the last conversation turns for the extraction prompt."""
    lines: list[str] = []
    for msg in messages[-_EXTRACTION_MESSAGE_TAIL:]:
        if isinstance(msg, HumanMessage):
            role = "USER"
        elif isinstance(msg, AIMessage):
            role = "ASSISTANT"
        else:
            continue
        content = msg.text if hasattr(msg, "text") else str(msg.content)
        if not content:
            continue
        lines.append(f"{role}: {content[:_EXTRACTION_MESSAGE_MAX_CHARS]}")
    return "\n".join(lines)


def _format_existing_loops(loops: list[Any]) -> str:
    """Render the user's OPEN loops with ids (closure targets + dedup context)."""
    if not loops:
        return "None."
    return "\n".join(f"- id={loop.id} [{loop.direction}] {loop.subject}" for loop in loops)


async def apply_extraction(
    extraction: OpenLoopExtraction,
    *,
    repo: OpenLoopRepository,
    user_id: UUID,
    session_id: str,
    settings: Any,
) -> dict[str, int]:
    """Apply extracted items with deterministic guards.

    Rules:
    - items capped to ``open_loops_extraction_max_items``;
    - ``close`` must target an id present in the user's OPEN loops (anything
      else — invalid UUID, foreign id — is skipped, never an error);
    - ``open`` refused beyond ``open_loops_max_open_per_user`` and for
      case-insensitive duplicate subjects;
    - ``due_hint`` parsed tolerantly (unparseable → None).

    Args:
        extraction: Structured LLM output.
        repo: Open-loop repository (caller owns the session/commit).
        user_id: Owner.
        session_id: Conversation thread id (stored as source_ref).
        settings: Settings view carrying the two caps.

    Returns:
        Counters ``{opened, closed, skipped}`` for logging/metrics.
    """
    existing = await repo.list_open_for_user(user_id, limit=settings.open_loops_max_open_per_user)
    existing_ids = {loop.id for loop in existing}
    existing_subjects = {loop.subject.strip().lower() for loop in existing}

    opened = closed = skipped = 0
    open_budget = settings.open_loops_max_open_per_user - len(existing)

    for item in extraction.items[: settings.open_loops_extraction_max_items]:
        if item.action == "close":
            try:
                target = UUID(item.loop_id) if item.loop_id else None
            except ValueError:
                target = None
            if target is None or target not in existing_ids:
                skipped += 1
                continue
            if await repo.close_loop(target, user_id, reason="conversational"):
                closed += 1
            else:
                skipped += 1
            continue

        # action == "open"
        subject_key = item.subject.strip().lower()
        if not subject_key or subject_key in existing_subjects or open_budget <= 0:
            skipped += 1
            continue
        await repo.create(
            {
                "user_id": user_id,
                "subject": item.subject.strip(),
                "counterparty": item.counterparty,
                "direction": item.direction,
                "due_hint": _parse_due_hint(item.due_hint_iso),
                "source_ref": session_id,
            }
        )
        existing_subjects.add(subject_key)
        open_budget -= 1
        opened += 1

    return {"opened": opened, "closed": closed, "skipped": skipped}


async def _run_extraction(
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    run_id: str,
) -> None:
    """LLM call + application, on a dedicated DB session."""
    from src.core.llm_config_helper import get_llm_config_for_agent
    from src.core.time_utils import get_prompt_datetime_formatted
    from src.domains.agents.prompts.prompt_loader import load_prompt
    from src.domains.open_loops.repository import OpenLoopRepository
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.llm import get_llm
    from src.infrastructure.llm.structured_output import get_structured_output

    owner_id = UUID(user_id)

    async with get_db_context() as db:
        repo = OpenLoopRepository(db)
        existing = await repo.list_open_for_user(
            owner_id, limit=settings.open_loops_max_open_per_user
        )

        system_prompt = load_prompt("open_loop_extraction_prompt").format(
            current_datetime=get_prompt_datetime_formatted(),
            max_items=settings.open_loops_extraction_max_items,
        )
        user_prompt = (
            f"CURRENT OPEN LOOPS:\n{_format_existing_loops(existing)}\n\n"
            f"CONVERSATION TAIL:\n{_format_messages_tail(messages)}"
        )

        llm = get_llm("open_loop_extraction")
        config = get_llm_config_for_agent(settings, "open_loop_extraction")
        token_capture = TokenCaptureHandler()
        extraction = await get_structured_output(
            llm=llm,
            messages=[
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ],
            schema=OpenLoopExtraction,
            provider=config.provider,
            node_name="open_loop_extraction",
            config=RunnableConfig(callbacks=[token_capture]),
        )

        # G-1: every LLM call is billed — persist the extraction spend.
        from src.infrastructure.proactive.tracking import track_proactive_tokens

        try:
            await track_proactive_tokens(
                user_id=owner_id,
                task_type="open_loop_extraction",
                target_id=run_id,
                conversation_id=None,
                tokens_in=token_capture.tokens_in,
                tokens_out=token_capture.tokens_out,
                tokens_cache=token_capture.tokens_cache,
                model_name=config.model,
            )
        except Exception as exc:  # noqa: BLE001 — tracking must not lose the extraction
            logger.warning("open_loop_token_tracking_failed", run_id=run_id, error=str(exc))

        stats = await apply_extraction(
            extraction,
            repo=repo,
            user_id=owner_id,
            session_id=session_id,
            settings=settings,
        )
        await db.commit()

    _store_extraction_debug(
        run_id,
        {
            "items_parsed": len(extraction.items),
            **stats,
            "items": [
                {
                    "action": item.action,
                    "subject": item.subject[:120],
                    "direction": item.direction,
                    "counterparty": item.counterparty,
                    "due_hint_iso": item.due_hint_iso,
                }
                for item in extraction.items[: settings.open_loops_extraction_max_items]
            ],
        },
    )
    logger.info(
        "open_loop_extraction_completed",
        run_id=run_id,
        user_id=user_id,
        **stats,
    )


async def extract_open_loops_background(
    *,
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    run_id: str,
) -> None:
    """Background entry point (safe_fire_and_forget contract: never raises).

    Guards: global flag, non-empty conversation. The caller
    (``response_node._schedule_post_response_extractions``) already gates on
    trivial messages and automated sources, mirroring the other extractions.

    Args:
        user_id: Owner user id (string form, graph plumbing).
        messages: Conversation messages (tail is used).
        session_id: Conversation thread id.
        run_id: Run id for logging correlation.
    """
    if not settings.open_loops_enabled:
        return
    if not messages:
        return
    try:
        await _run_extraction(user_id, messages, session_id, run_id)
    except Exception as exc:  # noqa: BLE001 — background task, degrade silently
        logger.warning(
            "open_loop_extraction_failed",
            run_id=run_id,
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )

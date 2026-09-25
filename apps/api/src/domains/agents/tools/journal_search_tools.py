"""Journal search tool — LIA re-reads its own journal on a subject (ADR-318).

The journal injected each turn is ranked on the person's MESSAGE; a subject the
turn discovers on the way reaches no entry that way. This tool looks such a
subject up through the one door (``journals/search``), under three gates read
at CALL time:

- the instance capability (``PlatformCapability.JOURNALS``: the deployment
  ceiling and the operator's switch, ADR-280);
- the person's own preference, read from their row — a voice lookup runs on a
  runtime that carries no preference, and its default would read « off »;
- a subject worth embedding.

Read-only, no HITL, no OAuth. Messages are technical English the model rewords
(ADR-256), and a lookup that could not run never reads as « nothing is noted »
(ADR-303). The entries returned count as injections — they reached a prompt,
which is what the consolidation reads the count as.
"""

from __future__ import annotations

from datetime import tzinfo
from typing import Annotated, Any, Final
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.time_utils import resolve_user_timezone
from src.domains.agents.constants import AGENT_JOURNAL
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.journal.catalogue_manifests import (
    JOURNAL_MAX_RESULTS_DESCRIPTION,
    JOURNAL_QUERY_DESCRIPTION,
    JOURNAL_SEARCH_QUERY_MIN_CHARS,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.lookup_parameters import bounded_count
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.journals.context_builder import track_injected_entries
from src.domains.journals.models import JournalEntry, JournalEntryLevel
from src.domains.journals.search import journal_enabled_for, search_journal

logger = structlog.get_logger(__name__)

#: What each abstraction level IS, in the words the model reads.
_LEVEL_KINDS: Final[dict[str, str]] = {
    JournalEntryLevel.L1.value: "directive",
    JournalEntryLevel.L2.value: "pattern",
    JournalEntryLevel.L3.value: "portrait_facet",
}


def _value(field: object) -> str | None:
    """The stored spelling of an enum column, or the string itself."""
    if field is None:
        return None
    return str(getattr(field, "value", field))


def _entry_item(entry: JournalEntry, score: float, zone: tzinfo) -> dict[str, str | float | None]:
    """One entry as the model reads it — the day it was written in the person's calendar."""
    level = _value(entry.level) or ""
    return {
        "title": entry.title,
        "content": entry.content,
        "theme": _value(entry.theme),
        "kind": _LEVEL_KINDS.get(level, level),
        "confidence": _value(entry.confidence),
        "written_on": entry.created_at.astimezone(zone).date().isoformat(),
        "relevance": round(score, 2),
    }


def _refusal(message: str, code: ToolErrorCode) -> UnifiedToolOutput:
    return UnifiedToolOutput.failure(message=message, error_code=code.value)


@read_tool(name="search_journal", agent_name=AGENT_JOURNAL)
async def search_journal_tool(
    query: Annotated[str, JOURNAL_QUERY_DESCRIPTION],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    max_results: Annotated[int | None, JOURNAL_MAX_RESULTS_DESCRIPTION] = None,
) -> UnifiedToolOutput:
    """Search LIA's own journal — what LIA noted from past conversations with the user.

    Directives ('WHEN … → DO …'), observed patterns and portrait facets. Search
    a subject the user's message does not name: the entries the message evokes
    already reach the answer. Empty means nothing is noted on it; a failure
    means the search could not run, never that nothing is noted.

    Args:
        query: The subject to look up.
        runtime: LangChain tool runtime (injected).
        max_results: Result ceiling, clamped to ``settings.journal_search_max_results``.

    Returns:
        UnifiedToolOutput with ``{entries: [...], count}``, most relevant first;
        a typed failure when journals are switched off or the search could not run.
    """
    config = validate_runtime_config(runtime, "search_journal_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    if not await is_capability_enabled(PlatformCapability.JOURNALS):
        return _refusal(
            "Journals are switched off on this instance: nothing was searched. Do not "
            "claim that nothing is noted.",
            ToolErrorCode.FORBIDDEN,
        )
    needle = query.strip()
    if len(needle) < JOURNAL_SEARCH_QUERY_MIN_CHARS:
        return _refusal(
            f"Give a subject to look up (at least {JOURNAL_SEARCH_QUERY_MIN_CHARS} characters).",
            ToolErrorCode.INVALID_INPUT,
        )
    user_id = UUID(str(config.user_id))
    if not await journal_enabled_for(user_id):
        return _refusal(
            "The journal is switched off in the user's settings: nothing was searched. "
            "Never say that nothing is noted.",
            ToolErrorCode.FORBIDDEN,
        )

    limit = bounded_count(max_results, settings.journal_search_max_results)
    results = await search_journal(
        user_id, needle, limit=limit, min_score=settings.journal_context_min_score
    )
    if results is None:
        return _refusal(
            "The journal search could not run right now (no embedding). Say it could not "
            "be checked; never conclude that nothing is noted.",
            ToolErrorCode.DEPENDENCY_ERROR,
        )
    if results:
        track_injected_entries([entry.id for entry, _score in results])

    zone = resolve_user_timezone(tool_runtime_context(runtime))
    entries = [_entry_item(entry, score, zone) for entry, score in results]
    # Counts only: the subject and the entries are about the person.
    logger.info(
        "journal_search_tool_completed", user_id=str(user_id), found=len(entries), limit=limit
    )
    # The list is capped at ``limit``: it names the most relevant entries and
    # never claims to be every match (ADR-185).
    return UnifiedToolOutput.data_success(
        message=(
            f"The {len(entries)} most relevant journal entr"
            f"{'y' if len(entries) == 1 else 'ies'} for this lookup (at most {limit})."
            if entries
            else "No journal entry matches this lookup."
        ),
        structured_data={"entries": entries, "count": len(entries)},
    )


__all__ = ["search_journal_tool"]

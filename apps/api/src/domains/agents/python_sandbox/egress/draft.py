"""The egress question, as a card (ADR-298).

A host nobody permitted is ASKED of the person, never refused in silence:
the tool hands the call back as a draft — the one shape both execution modes
already know how to draw and to answer — and the card names what the person
decides on: the hosts, the purpose the model stated, and a COUNT of the
turn's data. Three answers: allow with the turn's data, allow without,
refuse.

The card carries what the person reads and nothing else. The script and the
turn's items never leave the loop: the ReAct node that received this draft
settles the answer in place (``nodes/react_egress_question``) by handing it
to the very same tool call, re-invoked — so there is no replay to store, and
nothing of the code ever reaches a card, a prompt or the wire. The code stays
admin-only (ADR-249 §8).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from src.core.config import get_settings
from src.core.constants import PYTHON_SANDBOX_TOOL_NAME
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.python_sandbox.egress.hosts import HostDecision
from src.domains.agents.tools.output import UnifiedToolOutput

#: Registry item types that are not the person's DATA (a draft under review,
#: a chart the turn drew) — never counted on the card.
_NOT_DATA_TYPES = frozenset({"DRAFT", "CHART", "MCP_APP"})


def summarize_turn_data(
    items: Mapping[str, Any], *, max_bytes: int, language: str
) -> dict[str, Any]:
    """Count the turn's items by kind, and say whether they can travel.

    Args:
        items: The turn's registry items, by id.
        max_bytes: The stdin cap — beyond it nothing can travel.
        language: The reader's language, kept with the counts so the card
            names the kinds in it.

    Returns:
        ``{"counts": {kind: n}, "available": bool, "language": str}``.
    """
    counts: dict[str, int] = {}
    for item in items.values():
        kind = str((item or {}).get("type") or "").upper() if isinstance(item, Mapping) else ""
        if not kind or kind in _NOT_DATA_TYPES:
            continue
        key = kind.lower()
        counts[key] = counts.get(key, 0) + 1
    size = len(json.dumps({"items": items}, ensure_ascii=False, default=str).encode("utf-8"))
    return {"counts": counts, "available": size <= max_bytes, "language": language}


def ask_for_hosts(
    *,
    decision: HostDecision,
    purpose: str,
    items: Mapping[str, Any],
    language: str,
) -> UnifiedToolOutput:
    """Hand the call back as the egress question.

    Args:
        decision: The classification, with its unknown hosts.
        purpose: What the model said it computes.
        items: The turn's registry items — counted, never carried.
        language: The person's language.

    Returns:
        The draft output every draft path already understands.
    """
    from src.domains.agents.drafts.service import DraftService

    settings = get_settings()
    summary = summarize_turn_data(
        items, max_bytes=settings.skills_script_max_input_kb * 1024, language=language
    )
    unknown = list(decision.unknown)
    content: dict[str, Any] = {
        "hosts": list(decision.statuses),
        "hosts_unknown": unknown,
        "hosts_label": ", ".join(unknown),
        "purpose": purpose,
        "data_summary": summary,
    }
    return DraftService().create_draft(
        draft_type=DraftType.SANDBOX_EGRESS,
        content=content,
        source_tool=PYTHON_SANDBOX_TOOL_NAME,
        user_language=language,
    )


__all__ = ["ask_for_hosts", "summarize_turn_data"]

"""Post-response extraction debug aggregation (debug panel).

Single chokepoint for the fire-and-forget extraction families that expose a
pop-once debug cache keyed by run_id (journals, open loops). The SSE
generator (``agents/api/service.py``) emits one ``debug_metrics_update``
chunk per returned pair; a family without a cached result for the run is
simply absent. Adding a new extraction family means one entry in
``_FAMILIES`` here — zero churn at the emission site.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _families() -> list[tuple[str, Any]]:
    """(debug_metrics key, pop function) per extraction family, display order.

    Resolved lazily so importing this module never drags the extraction
    stacks (LLM clients) into contexts that only type-check or route.

    ``voice`` is a non-destructive READ, not a pop: the TTS records are still
    needed by the archive backfill, and ``cleanup_run_records`` releases them
    once the panel is done.
    """
    from src.domains.agents.services.open_loop_extractor import (
        pop_extraction_debug as pop_open_loops,
    )
    from src.domains.chat.run_records import get_tts_debug
    from src.domains.journals.extraction_service import (
        pop_extraction_debug as pop_journals,
    )

    return [
        ("journal_extraction", pop_journals),
        ("open_loop_extraction", pop_open_loops),
        ("voice", get_tts_debug),
    ]


def pop_background_extraction_debug(run_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Pop every populated extraction-family debug payload for a run.

    One failing family never loses the others (per-family isolation).

    Args:
        run_id: Pipeline run whose extraction results to collect.

    Returns:
        Ordered (debug_metrics key, payload) pairs — empty when nothing ran.
    """
    pairs: list[tuple[str, dict[str, Any]]] = []
    for key, pop in _families():
        try:
            payload = pop(run_id)
        except Exception as exc:  # noqa: BLE001 — debug-only, isolate families
            logger.debug("extraction_debug_pop_failed", family=key, error=str(exc))
            continue
        if payload is not None:
            pairs.append((key, payload))
    return pairs

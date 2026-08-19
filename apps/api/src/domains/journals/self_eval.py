"""Deferred self-evaluation funnel recording (audit 2026-08-19, lot 0).

The T → T+1 loop (inject directives, observe the user's reaction, signal
``evidence_outcome``) produced zero signals since April while every link
existed in the code. These helpers stamp the funnel stages so a wiring
defect and a never-signaling LLM stop being indistinguishable:

- ``no_previous_ids``  — extraction ran without T-1 injected ids;
- ``section_built``    — the directives section rendered with content;
- ``section_empty``    — ids were provided but no entry survived to render;
- ``signaled``         — the LLM emitted an outcome (counted BEFORE the
  hallucinated-id filter, so a dropped signal stays visible as a
  signaled-vs-applied gap — ``journal_evidence_total`` is the applied
  terminal, incremented by ``JournalService.update_entry``).
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from src.infrastructure.observability.metrics_journals import journal_self_eval_total

if TYPE_CHECKING:
    from src.domains.journals.schemas import ExtractedJournalEntry


def record_self_eval_funnel(previous_ids: list[str], section: str) -> str:
    """Record the head stage of the deferred self-evaluation funnel.

    Args:
        previous_ids: Journal entry ids injected at the previous turn.
        section: The rendered previous-turn directives section ("" when
            nothing survived to render).

    Returns:
        The recorded stage label (also the metric label).
    """
    if not previous_ids:
        stage = "no_previous_ids"
    elif section:
        stage = "section_built"
    else:
        stage = "section_empty"
    # Metrics are best-effort — never break the extraction pipeline.
    with suppress(Exception):
        journal_self_eval_total.labels(stage=stage).inc()
    return stage


def count_evidence_signals(actions: list[ExtractedJournalEntry]) -> int:
    """Count (and record) the evidence outcomes the LLM signaled.

    Counted BEFORE the hallucinated-id filter on purpose: a signal that the
    filter later drops must stay visible as a signaled-vs-applied gap.

    Args:
        actions: Parsed extraction actions.

    Returns:
        Number of update actions carrying an evidence outcome.
    """
    signaled = sum(
        1
        for action in actions
        if action.action == "update" and action.evidence_outcome in ("evidence", "contradiction")
    )
    if signaled:
        # Metrics are best-effort — never break the extraction pipeline.
        with suppress(Exception):
            journal_self_eval_total.labels(stage="signaled").inc(signaled)
    return signaled

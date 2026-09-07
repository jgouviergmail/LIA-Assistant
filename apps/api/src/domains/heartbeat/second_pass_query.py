"""Building the query that selects the second-pass sources.

Extracted from the aggregator on 2026-09-07, when the consultation recording
pushed that module past its ratchet cap. The cap is shrink-only by doctrine, so
the answer is an extraction — and this was never aggregator state to begin
with: it reads its argument and nothing else, which is a pure function wearing
a method's clothes.

The query is DYNAMIC on purpose (P8, ADR-135): the historical static one
anchored the same journals and the same memories cycle after cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.heartbeat.schemas import HeartbeatContext


def build_second_pass_query(context: HeartbeatContext) -> str:
    """Build a semantic search query from aggregated heartbeat context.

    Combines summaries of available context sources into a query that
    selects the most relevant journal entries AND user memories for
    this specific notification cycle (second-pass sources, P8).

    Args:
        context: Aggregated heartbeat context (calendar, weather, etc.)

    Returns:
        Query string for embedding-based semantic search
    """
    parts: list[str] = []

    if context.calendar_events:
        summaries = [e.get("summary", "") for e in context.calendar_events[:3]]
        parts.append(f"upcoming events: {', '.join(summaries)}")

    if context.weather_current:
        desc = context.weather_current.get("description", "")
        parts.append(f"weather: {desc}")

    if context.trending_interests:
        topics = [i.get("topic", "") for i in context.trending_interests[:3]]
        parts.append(f"interests: {', '.join(topics)}")

    if context.pending_tasks:
        tasks = [t.get("title", "") for t in context.pending_tasks[:3]]
        parts.append(f"tasks: {', '.join(tasks)}")

    if context.unread_emails:
        subjects = [e.get("subject", "") for e in context.unread_emails[:2]]
        parts.append(f"emails: {', '.join(subjects)}")

    # Fallback if no context available
    if not parts:
        return "user preferences observations patterns priorities"

    return " ".join(parts)

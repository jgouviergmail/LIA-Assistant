"""Activity domain — read-only "what LIA did for you" timeline.

Aggregates proactive events already persisted by other bounded contexts
(heartbeat, interests, journals, habits, open loops, reminders, scheduled
actions) into one chronological, paginated view. Pure read: no LangGraph,
no new tables, no LLM — briefing-style parallel fetchers with per-fetcher
DB sessions.

Phase: evolution program Lot 1-A1
Created: 2026-08-19
"""

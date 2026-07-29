"""Relations domain (N-09) — read-only personal CRM aggregation.

No LangGraph, no new table: like ``domains/briefing``, this bounded context
aggregates signals the user already owns (open loops, phone calls, birthdays,
memories) around the PEOPLE they concern, and reads them through independent
fetchers with per-source caching. Identity resolution is best-effort by design
(v1: exact then normalized name), surfaced honestly rather than pretended
authoritative — see ADR-176.
"""

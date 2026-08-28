"""Self-diagnostics bounded context (spec 2026-08-27).

Read-only aggregation over LIA's own telemetry — no LangGraph (briefing
pattern). Everything here is admin-only at its surfaces and inert unless
``settings.diagnostics_enabled`` is true.
"""

"""Product analytics bounded context (ADR-178).

Durable product truth: one row per useful result (``product_outcomes``) plus a
bounded lifecycle event log (``product_events``). PostgreSQL is the source of
truth for the North Star (E1/E2 states are mutable within the validation
window); Prometheus only transports bounded counters and DB-backed gauges
(``src.infrastructure.observability.metrics_product``).

No router: the domain has no user-facing API surface in v1 — outcomes are
recorded from internal chokepoints (chat run finalization, response feedback)
and consumed by Grafana dashboard 26.
"""

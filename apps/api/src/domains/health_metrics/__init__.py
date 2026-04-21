"""Health Metrics domain.

Ingests per-hour health metrics (heart rate, per-period step count, …)
sent by an iPhone Shortcut automation, persists them in PostgreSQL (timestamped
server-side at reception), exposes aggregation queries for visualization
(hour/day/week/month/year buckets), and manages per-user API tokens for the
ingestion endpoint.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

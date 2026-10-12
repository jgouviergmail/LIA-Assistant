"""Paid, opt-in qualification of JEV for semantic typing, taxonomy and ontology decisions.

Measurement code only (2026-10-11): nothing in this package is imported by the
application. Each decision point is judged on a calibration corpus (questions may
be tuned on it) and an independent corpus (judge only), against the deployment's
configured generative slot and, where one exists, the current mechanism. Every
paid call is pinned to the database configuration and settled in the instance
ledger. See docs/technical/JEV_SEMANTIC_QUALIFICATION.md.
"""

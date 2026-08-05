"""Habits bounded context — learned user rhythm and recurring requests (ADR-214).

Deterministic, per-user, explainable habit learning:

- ``UserHabitProfile``: one row per user, the nightly-recomputed rhythm
  profile (per-day-class presence histograms, claimed active windows,
  verdicts). Derived data — always recomputable from conversation history.
- ``UserHabit``: discrete promoted habits (active windows, locked recurring
  requests) with Bayesian feedback signals and user-controlled status
  (active / paused / blocked), mirroring the interests doctrine.

Nothing here writes on the chat hot path: the profile is recomputed by a
leader-elected nightly job, and recurring-request promotion happens from the
(pre-existing) recurrence ledger evaluation.
"""

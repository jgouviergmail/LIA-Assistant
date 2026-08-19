# ADR-232 — Closing the cognitive loops (journal self-evaluation, proactive guard, adaptive thresholds)

**Date**: 2026-08-19
**Status**: Accepted
**Context**: Production counter-audit of the four self-improvement loops
(semantics/ontology, personal journals, habits, proactive notifications),
every finding verified against prod data (PostgreSQL / Prometheus / Loki)
and by executed simulations (offline detector replay, real-LLM extraction
replay, Monte-Carlo of the quota scheduler).

## Findings that drove the decisions

1. **Journal self-evaluation was structurally silent.** Zero
   evidence/contradiction signals since April while every link existed:
   the funnel died on (a) a 10% injection rate (fixed global 0.63 threshold
   vs per-user score distributions massed at 0.53–0.61) and (b) the
   consolidation starving itself (min-entries floor of 3 vs journals pruned
   toward 2 — portraits stalled for months). A provoked replay with the
   real LLM proved the prompt sound: section present → signal emitted →
   counter applied.
2. **The proactive "don't interrupt" gate was dead code.** It read a
   phantom attribute (`last_chat_activity_at` exists on no model), fell
   back to a nonexistent `Message` class, and swallowed the ImportError
   into `success()`. Its green unit test posed the attribute on an
   un-specced MagicMock.
3. **The epistemic contract on journal confidence was decorative.** Six
   entries at `confidence=high` with `evidence_count=0` everywhere.
4. **Candidate selection for proactive ticks was unfair.** Unordered
   `LIMIT batch_size` with no feature-flag filter: disabled users consumed
   slots and heap order silently starved late-sorting users.

## Decisions

- **Self-eval funnel instrumented** (`journal_self_eval_total{stage}`:
  no_previous_ids | section_built | section_empty | signaled; terminal =
  `journal_evidence_total`), signals counted BEFORE the hallucinated-id
  filter; the T-1 verified ids now join the filter's known set.
- **Delta-driven consolidation eligibility**
  (`build_consolidation_eligible_users_query`): ≥ min-entries ACTIVE
  entries AND (never consolidated OR an entry touched since the stamp).
  `JOURNAL_CONSOLIDATION_MIN_ENTRIES_DEFAULT` 3 → 1. No churn loop: the
  stamp is written after the run's actions.
- **Epistemic clamp**: an L0/L1 entry cannot hold `high` with
  `evidence_count=0` (demoted to medium, counted). L2/L3 free —
  their evidence is cross-entry convergence.
- **Activity gate rebuilt as an injected port** (`ActivityProbe`): the
  schedulers wire `conversations/activity_probe.fetch_last_user_activity_at`
  (user-role, non-automated, bounded to the cooldown horizon). No silent
  swallow: probe failures propagate to the runner's per-user failure
  accounting. Wiring pinned by test on both schedulers.
- **Adaptive per-user thresholds** (`infrastructure/adaptive/`): a generic
  controller moves per-user similarity thresholds inside HARD per-perimeter
  bounds toward a target pass-rate band — one step per interval
  (hysteresis), observable (counter + effective value through the existing
  debug surfaces, ADR-184), kill-switch
  (`ADAPTIVE_THRESHOLDS_ENABLED`). First perimeter: journal injection
  (floor 0.55, ceiling 0.70, band 10–35%). State is advisory Redis
  (recurrence-ledger family): reads fail open to the static default.
- **Fair SQL candidate selection**: feature flag pushed into SQL +
  `ORDER BY random()`. The timezone SQL prefilter was evaluated and
  REJECTED (one corrupt tz row would kill the whole batch; the Python
  gate's cost is microseconds).
- **Planner/ReAct journal injections stay out of the evaluated loop** (by
  documented decision at both discard sites): the response-flow injection
  is the evaluated instance; merging in-loop copies would corrupt the T-1
  checkpoint semantics.
- **Habits: the enforced bar is published.** `effective_presence_bar`
  (single authority, ceil-rounded so publication never understates) exposed
  per class in the API schema and the settings panel. Publication only —
  recalibration stays with the simulation harness. Gate-rejection census
  (`habit_window_rejected_total{day_class,gate}`) makes "why zero habits"
  answerable from Grafana. `ProfileVerdict` extracted to the pure
  `verdicts` module so `rhythm.py` imports without the ORM chain.

## Requalified (no action, with evidence)

- Heartbeat decision cost: the context ALREADY carries recent
  notifications; 75% LLM skips are informed judgment at ~0.09€/7d — a
  deterministic pre-LLM gate would risk muting the channel for no gain.
- Response-feedback chips (B-02) and heartbeat feedback silence (D-02):
  affordance proven rendered on both live and history paths; the gap is
  adoption, not defect.
- `journal_level_distribution` staleness: the gauge refreshes every
  consolidation tick (5h) regardless of eligible users — the observed
  absence was a restart artifact.

## Dated debt

- Ambient rhythm block prose (`habits/ambient.py`) still inline: its
  conditional multi-line structure needs a sectioned-template pattern
  (rule 16) — extract with a dedicated design, not a hack.
- A real document→file identity bridge needs a `file_name` ontology type
  plus a truthful drive-side consumer; the drive `query` param is free
  text and must not be mislabeled.
- Prod `.env` pins `JOURNAL_CONSOLIDATION_MIN_ENTRIES=3` and lacks the
  `ADAPTIVE_*` block: deployment requires the owner's env update.

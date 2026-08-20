# ADR-238 — Proposals inbox and adaptive ReAct budget (bounded autonomy)

**Date**: 2026-08-20
**Status**: Accepted
**Context**: Evolution program Lot 5 ("autonomie encadrée"). Two gaps:
(1) a missed-routine offer (ADR-214) that the user did not act on in the
moment simply scrolled away — the one proactive artifact that asks for a
DECISION had no surface to be decided on; (2) the ReAct loop ran every
query, trivial or sprawling, under the same fixed iteration cap.

## Decision

- **C2 — proposals inbox, zero new authority**: the inbox is a VIEW over
  what already exists. An open proposal IS a heartbeat notification
  carrying a `habit_offer_id` and no `user_feedback`, inside
  `HEARTBEAT_OFFERS_WINDOW_DAYS` (old offers age out silently — a stale
  proposal is noise). `GET /heartbeat/offers` (pure builder
  `open_offers_stmt`, SQL-predicate-tested; exact total ADR-185).
  Deciding rides the EXISTING feedback endpoint: accept = 👍 then the
  chat opens PREFILLED with the offer (nothing auto-sends — HITL
  intact); decline = 👎. Both keep feeding the habit's Bayesian signals
  (ADR-214) — the inbox adds a surface, never a second authority. The
  hub gains a sixth, TOP section (a to-decide set outranks histories)
  and a sixth badge count in the single hub-counts read. PULL-only by
  design: listing costs no attention, so no eligibility gate applies.
- **C4 — adaptive ReAct budget** (`react_adaptive_budget_enabled`,
  default OFF — owner flips after observing): the configured
  `react_agent_max_iterations` becomes a CEILING; the per-turn budget is
  `base + (domains-1) × per_extra_domain` from the analyzer's domain
  span, computed once in `react_setup` and stored in the declared state
  key `react_max_iterations_effective` (the undeclared-key trap). The
  router falls back to the ceiling when the budget is absent — and on
  UNKNOWN complexity (empty domains) the budget IS the ceiling: the
  adaptive path only ever saves on provably simple queries, it never
  under-budgets a hard one.
- **B3 within-run (Reflexion verbal step)**: the repeated-call guard's
  block message now instructs the model to state IN ONE SENTENCE why the
  failed approach did not work before choosing the next action — the
  Reflexion pattern at its cheapest, riding a message that already
  interrupts the loop. Cross-session lessons stay on `procedural`
  extraction (ADR-236); no LLM call is added to any error path.

- **B4 groundwork — calibration evidence, not calibration**: registering
  a new adaptive perimeter (bounds, target band) stays an owner
  arbitration; what ships is the evidence that arbitration reads —
  `adaptive_candidate_top_score{perimeter}` (aggregate histogram, no
  per-user state, no threshold effect), first wired on the
  `memory_injection` candidate.

## Consequences

- The proposals section renders only when `heartbeat_enabled` (frontend
  gate mirrors the backend flag — ADR-061 gate-keeper).
- The hub's five-flat-sections arbitration (2026-08-03) gains a sixth
  member placed FIRST; flagged for the owner's next visual pass.
- Turning the adaptive budget on changes only WHEN the loop stops early
  on single-domain queries; every safety limit (compute budget,
  repeated-call guard, terminal threshold) is untouched.

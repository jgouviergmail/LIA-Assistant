# ADR-239 — Evolution program closure: requalifications and reserved arbitrations

**Date**: 2026-08-20
**Status**: Accepted
**Context**: Closing inventory of the 7-lot evolution program
(ADR-234..238). Lots 1-5 shipped; this ADR records, with evidence, why
the remaining items are either ALREADY SATISFIED by existing systems or
deliberately reserved for an owner arbitration — so future audits do not
re-propose them (the ADR-232 requalification doctrine).

## Requalified — verified already satisfied, no action

- **C1 (ambient, event-driven proactivity)**: conditional scheduled
  actions (ADR-175) already ARE the ambient loop — evaluators for
  `mail_match`, `weather_change`, `document_added`, `calendar_event`,
  `task_overdue`; per-fact idempotency (`ConditionVerdict.fingerprint`
  vs `condition_state.last_fingerprint` — the same fact never fires
  twice); scheduler cadence; the LLM only paid on an actual trigger.
  The plan's "automatic, no manual opt-in" variant is REJECTED on the
  sovereignty pillar: creating the conditional action IS the consent.
- **D2 / D3-PAD** (recorded in ADR-237): relationship-stage directives
  and the `<InnerVoice>` clause already modulate form.

## Reserved for owner arbitration (evidence ready, no code)

- **C3 (multi-day missions with milestones)**: background runs (ADR-117)
  and scheduled actions cover detached generation and recurrence; a
  MISSION (persistent goal, milestone reporting, resumability) is a new
  product object whose shape (what is a milestone? where does it
  report?) deserves a mockup-level arbitration before any schema.
- **C6 (producer-critic on high-stakes paths)**: human HITL already
  covers interactive mutations; the only candidate is the auto-approved
  scheduled-action path, which ALREADY records `last_error` and
  `consecutive_failures`. A recurring LLM critic without a measured
  false-success rate is speculative cost (YAGNI) — arbitrate WITH that
  evidence.
- **B5 (compiling recurrences into skills)**: the recurrence detector
  (P12/ADR-140) already proposes scheduled actions — compilation exists
  in its safest form. Compiling multi-step sequences into SKILLS is a
  product-voice decision (what a generated skill says and does) — same
  doctrine as D5: the owner sees the content before it ships. HITL
  remains mandatory whenever it does.
- **D3-channel / D5** (recorded in ADR-237): output-surface parameter
  and Big Five leanings registry.
- **B4 (new adaptive perimeters)**: the calibration evidence now
  accumulates (`adaptive_candidate_top_score{perimeter}`, ADR-238);
  registering a perimeter (bounds, target band) happens per perimeter,
  on that evidence.

## Consequences

- The program's shipped surface: ADR-234 (activity timeline), ADR-235
  (memory supersession), ADR-236 (procedural memory + repair), ADR-237
  (voice prosody + briefing readout), ADR-238 (proposals inbox +
  adaptive ReAct + candidate evidence).
- Every reserved item above carries its trigger: a mockup (C3), a
  measured false-success rate (C6), a content review (B5, D5), a
  perimeter-by-perimeter registration (B4), a display-mode
  reconciliation (D3-channel).

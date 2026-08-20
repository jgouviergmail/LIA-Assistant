# ADR-236 — Procedural memory: the assistant learns HOW to work for its user

**Date**: 2026-08-19
**Status**: Accepted
**Context**: LIA memorized facts about the user (six categories) but
nothing durable about how the user wants the ASSISTANT to behave. A
correction ("answer shorter", "stop suggesting X", "sign my emails like
this") evaporated with the conversation window; the same friction
returned every session. This is the LangMem "procedural memory" insight
mapped onto LIA's existing memory store — no new subsystem (Lot 3-B2/D6
of the evolution program).

## Decision

- **Seventh memory category `procedural`** (`MemoryCategory.PROCEDURAL`):
  an EXPLICIT standing instruction or correction about assistant
  behavior. Extraction criteria are strict (durable intent addressed to
  the assistant — never inferred from a one-off mood, never the user's
  own habits, which stay `pattern`). A contradicting new instruction
  emits an `update` on the old rule — which, since ADR-235, supersedes
  with a trail instead of overwriting.
- **Injected as binding directives, first after sensitivities**: the
  section headers file (single source of truth, completeness-asserted
  against the enum) gains `procedural|### RÈGLES DE FONCTIONNEMENT…`
  right after the sensitivity block — standing orders read before any
  factual section. No new injection mechanics: same profile, same caps,
  same retention scoring.
- **Correction repair directive (D6)** in
  `response_system_prompt_base.txt`: a fresh correction is acknowledged
  ONCE, plainly, without over-apology, and applied IN the same answer —
  "a visible change of behavior is the apology". The psyche side needed
  nothing: rupture-repair detection and its trust bonus were already
  wired (`PsycheService` → `detect_rupture_repair`).
- **Reflexion on tool failures (B3) is deliberately NOT shipped here.**
  The verified plumbing (typed `ToolErrorCode`, tool metrics) exists,
  but an automatic LLM self-critique on error paths needs the ReAct
  budget rework (evolution Lot 5-C4) to be cost-bounded, and a
  deterministic lesson string would be memory pollution. The
  cross-session lesson loop rides on `procedural` extraction until C4
  lands; revisit there.

## Consequences

- No migration: `category` is an open string column; the enum, the
  extraction prompt, and the headers file are the three synchronized
  authorities (the completeness test pins enum↔headers).
- Procedural rules obey the existing lifecycle: retention scoring,
  pinning, consolidation (same-category only), supersession (ADR-235),
  GDPR wipe.
- The user can read and delete every learned rule in the memories UI —
  a rule the user cannot see would be an enforced-but-hidden bound
  (ADR-184 doctrine).

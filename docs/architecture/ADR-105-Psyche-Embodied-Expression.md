# ADR-105: Psyche Embodied Expression Layer (A-E)

**Status**: 🎯 PROPOSED (implemented behind a flag, pending broader production validation)
**Date**: 2026-07-05
**Deciders**: jgouvier + Claude (pair analysis)
**Technical Story**: Sibling to [ADR-104](ADR-104-Psyche-De-Saturation.md). ADR-104 de-saturated the psyche *state*; this ADR fixes how that state is *expressed* in the response.

---

## Context and Problem Statement

Even after de-saturation (ADR-104) made the psyche state varied and appropriate, a blind evaluation exposed a second failure: the state did not reliably **transpire** in the reply. The shipped injection described the mood with **abstract adjectives** — `MOOD: melancholic (noticeably)` + "quiet, measured, gentle". A strong-voiced personality (Cynic) simply ignored them: forced into a melancholic state, its reply was **as bright and verbose as with no injection at all**. The mood was invisible.

The original design principle ("show, don't tell") was right, but the *mechanism* was an adjective the LLM does not act on.

**Question**: How do we make the psyche state perceptible in the response — reliably, across personalities and moods — without the assistant naming its state or changing the facts?

---

## Decision Drivers

1. Make the state perceptible in HOW the assistant speaks (not WHAT it says).
2. Work even when it must push AGAINST a personality's default (e.g., make a sarcastic Cynic subdued).
3. Preserve the hard guardrails: never "I feel", never guilt-trip, never attribute to the user, facts unchanged.
4. Reversible (instant `.env` rollback for a live-feature behaviour change).

---

## Considered Options

### Option 1 (chosen): Embodied voice grammar (A-E)
Replace the adjective directives with an `<InnerVoice>` block that (A) gives **concrete form moves** — opening, sentence length, rhythm, register, energy, licence to be brief/expansive; (C) frames the state as *the voice this turn*, not a label to note; (D) reconciles it with `<Personality>`; (B, E) grants explicit authority over presentation form (length, number of suggestions).
- ✅ Blind evaluation: the human picked the embodied version for **both** tested moods; for melancholic it was the *only* option that read subdued (adjective + no-injection both stayed bright).
- ✅ Concrete moves override the personality's default where adjectives could not.
- ❌ Slightly longer prompt block; a strongly playful personality still co-emits high-energy emotions, so the deepest low-arousal register remains partly personality-gated (character-faithful).
- **Verdict**: ✅ ACCEPTED, default on, behind `PSYCHE_EMBODIED_INJECTION`.

### Option 2 (rejected): Keep adjective directives, tune wording
- ❌ The blind test showed the failure is structural (adjective vs observable behaviour), not wording.

### Option 3 (rejected): Post-hoc rewrite pass
- ❌ A second LLM call to "re-tone" the answer — extra latency/cost, and the tone belongs in the generation, not a rewrite.

---

## Decision Outcome

**Chosen**: the embodied `<InnerVoice>` grammar, default on, with the legacy graduated format retained behind `PSYCHE_EMBODIED_INJECTION=false` as an instant rollback.

### Implementation
- `MOOD_EXPRESSION_GRAMMAR` — concrete form grammar per mood (all 14; boot-time completeness assert, ADR-085 pattern) — `psyche/constants.py`.
- `PsycheEngine.format_embodied_prompt_injection(profile)` — returns `(dynamic_block, frame_template_name)`, mirroring `format_graduated_prompt_injection` so the engine stays pure. The dynamic block = personality reconciliation + mood grammar + single emotion lead + relationship + drives + confidence hedging (on genuinely weak domains) + evolution + intensity lean; 2-tier graduation (compact "faint" below 0.20 magnitude) — `psyche/engine.py`.
- The static scaffolding — the `<InnerVoice>` wrapper, the "you MAY reshape the form" authority, and the hard anti-tell guardrails — lives in **versioned** prompt files `psyche_embodied_frame.txt` / `psyche_embodied_faint.txt` (a single `{dynamic}` placeholder), loaded and substituted by `service.process_pre_response`, which branches on `settings.psyche_embodied_injection`.
- Response prompt: the `<InnerState>` "tone-calibration / invisible" wrapper is removed (the `<InnerVoice>` block is self-framing); `<ResponseGuidelines>` gains a clause that `<InnerVoice>` MAY modulate presentation form (never facts) — `response_system_prompt_base.txt`.
- **Proactive channels** (heartbeat, reminders, voice comments, interest content, fallback) also get A-E: `build_psyche_prompt_block` renders the same `MOOD_EXPRESSION_GRAMMAR` through a lighter versioned frame `psyche_embodied_proactive.txt` (short-message form — no drives/suggestions), flag-gated. Their five caller prompts drop the `<InnerState>` "tone-calibration / invisible" wrapper for the self-framing `<InnerVoice>` block. Validated: the same reminder reads subdued when melancholic, punchy when energized.
- Dead `format_rich_prompt_injection` deleted. `format_graduated_prompt_injection` + `psyche_usage_directive*.txt` retained (the flag's rollback path).
- Tests: 7 deterministic tests (all-moods grammar, personality reconciliation, emotion lead, anti-tell, form authority, faint level, intensity lean). No migration.

### Consequences
- ✅ The mood is perceptible in the reply; a Cynic forced melancholic now reads genuinely subdued.
- ✅ Instant `.env` rollback; the pre-A-E format still exists behind the flag.
- ❌ Two injection formats coexist until the flag is retired (planned once prod-validated).
- ⚠️ Evidence is 1 message × 1 personality × 2 moods × 1 human judge — clean but not broad. Broader prod validation pending.

---

## Validation

**Blind eval (2026-07-05, Cynic, gemini-2.5-flash, "résume un bail")**: same message, forced mood, 3 modes (none / graduated / embodied). The human blind-picked **embodied** for melancholic (the only subdued rendering) and for energized (tighter momentum vs the graduated 6-point sprawl).

**Acceptance criteria**:
- [ ] Broader blind rounds (other messages, Friend/Enthusiastic, tender/serene).
- [ ] Production A/B or re-measurement confirms perceptibility without uncanny/guilt-trip reports.
- [ ] Retire `PSYCHE_EMBODIED_INJECTION` + the graduated format once validated.

---

## Related Decisions
- [ADR-104: Psyche De-Saturation](ADR-104-Psyche-De-Saturation.md) — the state must be varied for expression to have anything to render; done first.
- [ADR-068: Psyche Engine](ADR-068-Psyche-Engine.md) — the original "show, don't tell" principle this refines.

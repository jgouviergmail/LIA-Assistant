# ADR-104: Psyche De-Saturation — Fixing the Confined-Mood Failure at the Source

**Status**: 🎯 PROPOSED (implemented, pending Phase-2 empirical validation before deploy)
**Date**: 2026-07-05
**Deciders**: jgouvier + Claude (pair analysis)
**Technical Story**: Follow-up to [ADR-068](ADR-068-Psyche-Engine.md). Trigger: user report that the assistant's mood/emotions never *transpire* in responses despite the rich v1/v2/v3 modeling.

> **Why this ADR exists**: the changes below rest on hypotheses that can only be fully
> confirmed once enough production data accumulates under the new configuration. This
> document is the **precise, versioned context** to revisit for analysis and corrective
> action. It records the production baseline, the root-cause analysis, the actions taken,
> the two contested judgment calls, and an explicit **readjustment decision matrix**.

---

## Context and Problem Statement

The Psyche Engine (ADR-068) models a rich psychological state (14 moods, 22 emotions, Big Five, drives, relationship). Yet users perceive **no** mood/emotion in the assistant's replies. A 3-month production data analysis (2026-04-02 → 2026-07-05, `psyche_history`, 749 `message` snapshots, 3 users; 1 dominant: 723 msgs on the **Cynic** personality, relationship STABLE, 288 interactions) proved the failure is **not weak modeling** — it is **confinement / saturation**:

| Measure | Production v1 | Interpretation |
|---|---|---|
| PAD magnitude | avg **0.777**, min **0.386** | 100% of messages in the *rich* (33%) or *intense* (67%) injection band; never calm |
| Octant | **100% A+ D+** (71% P+A+D+, 29% P−A+D+) | mood never leaves the high-arousal / high-dominance hemisphere |
| Moods reached | **4 of 14** (determined 59%, defiant 21%, energized 16%, playful 3%) | 10 moods — all calm/soft/low-arousal — computationally unreachable |
| Dominant emotion | **pride 61%** (active 88%) | mono-emotion; hype-man affect |
| Dead emotions | **gratitude, empathy, nervousness, wonder = 0** occurrences | soft/warm register absent (serenity 9.5%, tenderness 2.8%, concern 2.1%) |
| Emotion intensity | **61.5% ≥ 0.60** | almost never subtle |
| Dominant-emotion stickiness | **78.9%** same as previous turn | invariance |
| Simultaneous active emotions | avg **4.52** | undifferentiated emotional "blob" |
| Axis mobility | Pleasure ∈ [−0.94, +1.00]; Dominance ∈ [**+0.368**, +0.92] | **P is dynamic; A and D are locked positive** |
| Lifetime trend | emo_intensity 0.40 (Apr) → 0.75–0.88 (May–Jul); resonance 0.15 → 0.06 | **worsens over time** (opposite of "evolving") |

**Root-cause mechanisms identified (code-level):**

1. **Automatic pride pulse.** `compute_proactive_emotions` injected `pride:0.15` whenever any self-efficacy domain had `score>0.75 & weight>4.0`. Self-efficacy saturates for any established user ⇒ the pulse fired on **every** pre-response ⇒ pride pinned permanently ⇒ 61% dominant.
2. **Dominance one-way ratchet.** Only Pleasure has restoring forces (circadian, contagion, counter-regulation). Arousal and Dominance are only pulled by the slow inter-session temporal decay — but 81% of messages are bursts <30min apart where decay ≈ 0. High-D emotions (pride +0.30, determination +0.40, resolve +0.45) push D up with nothing pulling it back.
3. **High resting baseline.** The raw Mehrabian mapping has a strong `+0.60·C` dominance term. Cynic (C=0.55) rests at **D ≈ 0.40** — the observed floor (`min_D=0.368`). The mood decays *toward* this high baseline; even after 24h+ idle, magnitude only falls to ~0.49.
4. **Biased self-report.** The `<psyche_eval>` prompt said "if user positive (V>0.3) avoid negative emotions" and never surfaced the soft/warm register ⇒ the LLM reported almost exclusively bright, high-arousal, high-intensity emotions.
5. **Emotional blob.** `max_active=7` + slow `0.6·old+0.4·new` blend + `decay=0.3` kept ~4.5 similar emotions co-active, blending into one undifferentiated flavor.

What **works** and must not regress: relationship depth (0.50→0.86) and trust (0.44→0.67) genuinely evolve; Pleasure reacts to the user's tone.

**Question**: How do we de-saturate the psyche so mood/emotion become varied and perceptible, without breaking the "show-don't-tell / no guilt-trip / no attribution-to-user" guardrails, without harming task correctness, and reversibly?

---

## Decision Drivers

### Must-Have (Non-Negotiable):
1. Attack the **root cause** (what emotions get *created*), not symptoms.
2. **Reversible** — every threshold in `.env` (no rebuild to re-tune in prod).
3. Preserve guardrails: no "I feel X" unsolicited, no guilt-trip, no attribution-to-user (ADR-068 v3), facts unchanged.
4. No regression on relationship evolution or Pleasure dynamism.
5. No DB migration for the core (keep it low-risk).

### Nice-to-Have:
- Reach the low-arousal / calm register (serene, tender, reflective) when contextually appropriate.
- Personality fidelity (a Cynic *should* rest assertive; a Friend *should* reach warmth).

---

## Considered Options (per mechanism)

### Pride monoculture — Option A (chosen): remove the auto pride-pulse
**Approach**: delete the self-efficacy → pride injection; pride is earned only via the LLM appraisal.
- ✅ Kills the proven #1 cause; pride regains signal value; frees an emotion slot; removes a constant D-inflation source.
- ❌ Loses the intended "quiet baseline pride of a competent assistant"; severs the self-efficacy→emotion channel; risk of **over-correction** (pride → too rare); asymmetry vs the kept curiosity/enthusiasm/joy pulses.
- **Rejected alternatives**: *cap/guard* (`_existing("pride")<0.50`) — measured to still pin pride at 0.50 permanently; *weak version* — still ever-present, clutters the 4-slot palette; *cooldown* — cleanest "occasional pride" but needs a new DB column + migration (deferred).
- **Verdict**: ✅ ACCEPTED (with cooldown as the documented fallback if pride becomes too rare).

### Within-burst ratchet — Option F1 (ENABLED at 0.15): asymmetric relaxation
**Approach**: per-interaction pull toward baseline, **asymmetric** (only rabbits down axes *above* baseline; leaves below-baseline excursions free).
- ✅ Anti-ratchet without muting genuine calm/sad moments.
- **Verdict**: ✅ ACCEPTED, DEFAULT `0.15`. **This reverses an earlier call.** A synthetic sim (hand-fed a balanced emotion stream) suggested F1 compressed variety, so it first shipped OFF. Phase-2a end-to-end testing with a **real LLM** overturned that: the self-report keeps emitting the personality's characteristic high-arousal emotions (Cynic → amusement+determination; Friend → enthusiasm) turn after turn, and with F1 OFF arousal/dominance ratcheted monotonically up to **A=0.84, D=0.80** over 16 turns (the synthetic "extra moods" were an artifact of that drift, not real variety). F1=0.15 bounds the climb (A stabilised ~0.44) AND — being asymmetric — still let a sustained calm/sad conversation drive arousal negative (**−0.43**), reaching serene/reflective/resigned. Rejected: *symmetric* (mutes sadness), *off* (real-LLM ratchet), *full removal* (loses the anti-ratchet).

### Resting baseline too high — Option F2 (chosen): baseline damping
**Approach**: multiply the computed PAD baseline magnitude by a factor (default `0.75`), preserving relative personality differences.
- ✅ Lowers the pathological high-C dominance baseline (Cynic 0.40→0.30) ⇒ rest leaves the *rich* injection band (0.41→0.27 magnitude).
- ❌ Uniform (not D-specific); mildly compresses already-mobile personalities (Friend).
- **Verdict**: ✅ ACCEPTED. Rejected: *reduce the Mehrabian `0.60·C` coefficient directly* (more invasive, changes documented mapping — deferred as a Phase-2 candidate).

### Emotional blob — Option F4 (chosen): faster turnover
`PSYCHE_EMOTION_MAX_ACTIVE` 7→**4**, `PSYCHE_EMOTION_DECAY_RATE` 0.3→**0.4**. ✅ smaller, more differentiated active set. ❌ mild.

### Biased self-report — Option F6 (chosen): debias the appraisal prompt
**Approach**: rewrite `psyche_self_report_instruction.txt` — full palette with concrete triggers (gratitude/empathy/serenity/tenderness), explicit anti-default-to-pride/enthusiasm, intensity as a real dial (0.2–0.4 for routine). This fixes the **source** of the emotion stream.
- ✅ The single highest-leverage change (only a real LLM exercises it).
- ❌ **Not deterministically testable** — its effect is the core Phase-2 unknown.
- **Verdict**: ✅ ACCEPTED.

---

## Decision Outcome

**Chosen**: source-level de-saturation — remove the auto pride-pulse (**F3**) + debias the self-report (**F6**), supported by baseline damping (**F2**) and faster turnover (**F4**); asymmetric relaxation (**F1**) implemented but off by default.

**Justification**: The saturation was *created* by what emotions the engine/LLM produced (constant pride, biased high-intensity reports), not by insufficient damping. Fixing the source is more principled and avoids the symptom-level over-damping that measurably reduces variety.

### Implementation (shipped parameters)

| Knob (`.env`) | v1 | v2 (this ADR) | Fix |
|---|---|---|---|
| *(auto pride-pulse)* | on | **removed** | F3 |
| `PSYCHE_BASELINE_DAMPING` | (1.0 implicit) | **0.75** | F2 |
| `PSYCHE_AD_RELAXATION` | (n/a) | **0.15** (asymmetric anti-ratchet) | F1 |
| `PSYCHE_EMOTION_MAX_ACTIVE` | 7 | **4** | F4 |
| `PSYCHE_EMOTION_DECAY_RATE` | 0.3 | **0.4** | F4 |
| `psyche_self_report_instruction.txt` | biased | **debiased** | F6 |

**Files**: `src/domains/psyche/engine.py` (compute_pad_baseline damping, apply_appraisal asymmetric relaxation, compute_proactive_emotions pride removal), `src/domains/psyche/service.py` (wiring), `src/core/config/psyche.py`, `src/core/constants.py`, `src/domains/agents/prompts/v1/psyche_self_report_instruction.txt`, `.env*.example`. Tests: `tests/unit/domains/psyche/test_desaturation.py` (8, deterministic). No DB migration.

### Consequences

**Positive**:
- ✅ Removes the proven monoculture; emotion becomes a signal again.
- ✅ Cynic escapes the 2-mood lock (→3+ incl. calmer moods); resting magnitude 0.41→0.27.
- ✅ Fully `.env`-tunable, no migration, reversible.

**Negative**:
- ❌ Reliance concentrated on **F6** (a prompt) — validated in Phase-2a end-to-end, but a prompt can drift with model changes.
- ❌ Whether the deep-calm register is reached depends on personality: a *cynic* on a grief conversation reached serene/reflective/melancholic; a *playful friend* stayed warm-tender with light energy (co-emitted playfulness keeps arousal up). Both are character-faithful, but a strongly playful/upbeat personality will rarely show the low-arousal register.

**Risks**:
- ⚠️ **Over-correction**: pride measured at 0–12% in Phase-2a (target 15–30%) — slightly low; acceptable because pride still fires on genuine achievement, but worth watching in production.
- ⚠️ Phase-2a uses **scripted** conversations (~10–16 turns), a strong proxy but not months of real usage — production re-measurement still required.

---

## Validation

**Phase 2 (two distinct experiments, inline, before deploy):**
1. **End-to-end dynamics simulation** — real multi-turn conversations through the full pipeline (new engine + F6), measure the *evolved* state and compare to the v1 baseline below. This is what validates the de-saturation decisions.
2. **A-E blind expression eval** — forced mood states → responses with/without an "expression grammar" layer → human blind judging. (Tests a *separate* question: is the expression layer worth building. Does **not** test de-saturation, because it forces states.)

**Phase-2a results (2026-07-05, real LLM = gemini-2.5-flash, Cynic + Friend, scripted convos):**
- Pride dominant share: **61% → 0–12%** ✅ (monoculture destroyed; pride still fires on genuine achievement).
- Palette opened ✅: empathy, gratitude, concern, protectiveness, serenity, tenderness, melancholy, enthusiasm, playfulness, curiosity all emitted (were ~0 in prod).
- Intensity ≥0.60 share: **61% → 0–50%** ✅ (context-dependent; 0% on a calm conversation).
- Personality differentiation ✅: Cynic → assertive/amused (upbeat) and reflective/serene/melancholic (grief); Friend → playful/enthusiastic (upbeat) and warm/tender (calm).
- Low-arousal register reachable ✅: on a sustained grief conversation the Cynic mood reached serene/reflective/resigned with arousal down to **−0.43** (impossible in prod, where A was always positive and D never < 0.37).
- F1 decision reversed (see F1 option): re-enabled at 0.15 after observing the real-LLM ratchet.

**Metrics to track (baseline → target):**
- Pride dominant share: **61% → 15–30%** (not ~0%).
- Distinct moods visited (per active user): **4 → ≥ 7 / 14**.
- Octant coverage: **0% A− or D− → > 0%** under calm/soft exchanges.
- Dead emotions (gratitude/empathy/nervousness/wonder): **0 → reachable**.
- Emotion intensity ≥0.60 share: **61.5% → < 40%**.
- Resting magnitude after idle: **0.49 → < 0.35**.
- Relationship depth/trust growth: **preserved** (no regression).

**Acceptance Criteria**:
- [ ] End-to-end sim shows pride share in [15%, 35%] and ≥6 distinct moods.
- [ ] No monotonic A/D climb over a 50+ turn session (else raise `PSYCHE_AD_RELAXATION`).
- [ ] Soft/warm emotions appear on appropriate exchanges.
- [ ] Post-deploy **production re-measurement** (rerun the ADR-104 baseline queries) after ≥ 1 month.

### Readjustment Decision Matrix (revisit with data)

| Observation after data | Root interpretation | Corrective action |
|---|---|---|
| Pride share < 5% / assistant feels flatly un-confident | F3 over-corrected | Re-add a **cooldowned** pride pulse (needs `last_pride_pulse_at` column + migration) |
| A/D climb over long sessions returns | source fix insufficient alone | Set `PSYCHE_AD_RELAXATION` = 0.10 (asymmetric net already in place) |
| Still too few moods / rests too assertive | damping too weak for high-C personalities | Lower `PSYCHE_BASELINE_DAMPING` (0.75→0.6) **or** reduce the Mehrabian `0.60·C` term |
| Emotions still blob together | turnover too slow | Lower `PSYCHE_EMOTION_MAX_ACTIVE` (4→3), raise `PSYCHE_EMOTION_DECAY_RATE` |
| Soft register still never reached | self-report still bright-biased | Strengthen F6 wording; consider per-axis (D-specific) damping |
| Bright affect now too rare / mixed emotions incoherent | F6 over-corrected | Soften F6 anti-bright wording |

---

## Related Decisions

- [ADR-068: Psyche Engine](ADR-068-Psyche-Engine.md) — the system this refines (baseline mapping, pride pulse, self-report all originate there).

## References

- Production baseline: `psyche_history` aggregate analysis, 2026-04-02 → 2026-07-05 (queries reproducible against the `psyche_history` / `psyche_states` tables).
- Mehrabian (1996) Big Five → PAD mapping; ALMA (Gebhard 2005).
- Superseded expectation: ADR-068 claimed "Assistant develops a perceptible, evolving personality" — production data showed it did not; this ADR is the corrective.

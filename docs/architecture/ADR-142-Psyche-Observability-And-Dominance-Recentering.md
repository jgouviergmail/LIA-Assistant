# ADR-142: Psyche Observability & Dominance Recentering

**Status**: ✅ IMPLEMENTED (2026-07-22) — knobs shipped inert · ✅ **ACTIVATED (2026-08-29)** — production baseline measured, both knobs promoted to code defaults and applied on every environment
**Date**: 2026-07-22
**Deciders**: jgouvier + Claude (pair analysis)
**Technical Story**: Follow-up to [ADR-104](ADR-104-Psyche-De-Saturation.md) / [ADR-105](ADR-105-Psyche-Embodied-Expression.md). Trigger: evaluation of the external `kindalive` project as an enrichment source for mood/emotion naturalness.

---

## Context and Problem Statement

ADR-104 (v1.21.10, 2026-07-05) de-saturated the psyche state and required a **production re-measurement after ≥ 1 month** — but the measurement instrument was never written, so the corrective has never been confronted with reality. While evaluating `kindalive` (github.com/smithandrewjohn/kindalive) as an enrichment source, a deterministic replay of the real `PsycheEngine` (service-faithful wiring, scripted appraisal streams) plus a computation over the real 14-personality catalogue exposed two defects ADR-104 did not address:

1. **The dominance axis is structurally off-center.** At the shipped damping (0.75), ALL 14 catalogue personalities rest at D > 0 (spread **+0.063..+0.349**, mean **+0.216** — confirmed live against the dev DB by the new instrument). The personality literally named *Dépressif* (N=0.85, pleasure override −0.20) rests in `neutral`, on the assertive side. Five mood centroids require D < 0 (`agitated`, `melancholic`, `content`, `overwhelmed`, `tender`) and are unreachable at rest for every personality. **Damping cannot fix this**: it is a homothety — it preserves the sign and relative proportion of every axis, so a catalogue resting entirely at D > 0 stays entirely at D > 0 at ANY damping value. The needed operation is a **translation**. Live dev data confirms the lock: the main dev user (290 message snapshots) visits 4/14 moods, 100% of snapshots in the P+A+D+ octant, dominant-emotion stickiness 99.3%.
2. **The proactive joy pulse crowns an emotion the appraisal did not report.** Deterministic replay measured the sustained-quality joy pulse firing on 40/60 ordinary-regime turns, making `joy` the dominant emotion 55% of the time — including under a stream where the LLM only ever reported `determination`/`amusement` (joy still dominant 47%). This is the same distortion mechanism as the pride pulse ADR-104 removed (61% dominant in production); the joy pulse was simply overlooked.

**kindalive verdict**: its neurochemical substrate mechanisms were tested against our engine and **rejected** — per-axis time constants changed nothing under burst regimes (mood variety 3→3, D floor unchanged) and its strict symmetric equilibrium *reduced* variety (moods 3→2). Its value was analytical: the principle "the resting point must leave headroom on both sides of every axis" is what exposed the D-centering defect. Lens kept, architecture not imported.

**Question**: How do we (a) finally make psyche claims measurable, and (b) fix the two proven defects — without a third blind tuning pass, without regression risk, and reversibly?

---

## Decision Drivers

1. **Never tune blind again** — ADR-068 and ADR-104 both shipped confident and unmeasured; the instrument comes first and gates activation.
2. **Merge must be a provable no-op** — settings default to today's behavior; a golden characterization test proves it.
3. Desired properties become **CI-enforced rules**, not hand-tuned numbers a future edit can silently break.
4. No migration, no frontend change, no i18n change (all 14 moods already have colors/emojis/translations ×6 — verified).
5. Engine purity preserved (`PsycheEngine` never imports settings — parameters with no-op defaults).

---

## Considered Options

### Fix the D-lock — Option A (chosen): post-damping translation `PSYCHE_DOMINANCE_CENTER`
`d = clamp(d_damped − center)`, applied after the override blend and damping. Default **0.0** (inert). Recommended activation **0.20**, *derived* from the measured catalogue mean (+0.216), not guessed.
- ✅ Recenters where the homothety cannot: at 0.20, 7/14 personalities rest D < 0 with the D-ordering **exactly** preserved (proven by test); override-based characters (JARVIS/Trump/Adolescent) keep their assertive lean.
- ✅ CI oracle: the scripted ordinary regime goes from 3 moods / 87% `determined` to 5 moods / top 40%.
- ❌ Character-fidelity trade-off: at 0.20 the Cynic's ordinary regime barely visits `determined` (1/30 turns) — activation review must check each personality's characteristic register survives; `pad_dominance_override` is the per-personality compensation, 0.15 the gentler fallback.
- **Rejected alternatives**: *stronger damping* (measured incapable — homothety); *reduce the Mehrabian `+0.60·C` term* (changes documented mapping, affects all axes' balance — deferred); *per-personality manual overrides for all 14* (14 hand-tuned numbers instead of one derived one).

### Fix the joy distortion — Option B (chosen): gate `PSYCHE_PROACTIVE_JOY_PULSE`
Default **true** (inert). Ablation proved removal changes NO mood metric (identical to 1e-2) — pure gain on emotion truthfulness. `curiosity` (new-relationship-scoped) and `enthusiasm` (anti-inflation-guarded, ~1/60) pulses are kept: measured near-inert and legitimately scoped.

### Rejected wholesale: kindalive mechanisms
Per-axis time constants (τ_A = 20 min): **refuted by ablation** — within bursts the emotion push dominates any decay rate; between sessions both regimes fully re-converge. Symmetric equilibrium: **counter-indicated** (variety 3→2; ADR-104's asymmetric choice was right). Chemical substrate: adds a migration + full re-validation for no benefit the targeted fixes don't deliver. Direct-to-LLM chemical interface: strictly worse than the emotion-vocabulary appraisal (models have priors on emotions, none on neurochemistry).

---

## Decision Outcome

**Chosen**: measurement instrument + two inert knobs + CI guards; activation is a separate, measured decision.

### Implementation (all inert at merge; defaults promoted 2026-08-29 — see Activation below)

| Deliverable | Where |
|---|---|
| `PSYCHE_DOMINANCE_CENTER` (shipped default 0.0 → **0.20 since 2026-08-29**) | `core/constants.py`, `core/config/psyche.py`, `engine.compute_pad_baseline(dominance_center=)`, 6 call sites in `psyche/service.py`, `.env*.example` |
| `PSYCHE_PROACTIVE_JOY_PULSE` (shipped default true → **false since 2026-08-29**) | same chain; `engine.compute_proactive_emotions(joy_pulse_enabled=)`, 1 call site |
| Measurement instrument (read-only, no PII) | `apps/api/scripts/measure_psyche.py` — ADR-104 battery per user (moods visited, octants, D<0/A<0 shares, dominant-emotion distribution with joy/pride flags, intensity ≥ 0.60 share, stickiness, co-active mean, post-idle magnitude) + live catalogue resting table. Placement inside the api build context (`Dockerfile.prod` does `COPY . .`) so `docker exec lia-api-prod python scripts/measure_psyche.py` works — repo-root `scripts/` does not ship |
| CI guards | `tests/unit/domains/psyche/test_mood_reachability.py` — golden characterization of the RAW mapping (14 resting PADs frozen at 1e-9, center pinned to 0.0 so the activation knob translates without altering it), a companion test pinning the shipped defaults to the activated values, catalogue-straddle guard at 0.20 (≥5 each side, ordering preserved, P/A untouched) plus a straddle check on the shipped default itself, and a deterministic end-to-end reachability oracle (locked at 0.0 / unlocked at 0.20) |
| Honesty micro-fixes | `repository.update` docstring (claimed nonexistent optimistic locking; known writer race documented), `models.py` trait/narrative/trait_snapshot Python comments (SQL `comment=` kept verbatim to avoid model/DB drift — reconcile in the next periodic comment-reconciliation migration, pattern `2026_07_13_1710`) |

Tests: 24 new (5 center + 3 gate + 9 guards + 12 aggregators, minus overlaps), psyche domain suite 207 green. Script proven in-container against the dev DB. No migration, no frontend file, no i18n key.

### Epistemic caveats (explicit)

- Simulated magnitudes (55% joy share, 3→5-6 moods) come from **synthetic** appraisal streams; ADR-104 documents a synthetic-sim conclusion (F1) that real-LLM testing overturned. The §resting-point facts and the live-DB confirmation do NOT depend on the streams. This is why measurement gates activation.
- The appraisal-prompt layer (self-report bias) and expression layer (ADR-105) remain unmeasured in production; they are OUT of scope here and must not be conflated with the state-layer effects at activation time.

### Activation procedure (the missing ADR-104 step) — EXECUTED 2026-08-29

1. ✅ **Baseline measured on production** (`measure_psyche.py`, 90-day and 30-day windows, 769 snapshots / 3 users). This doubles as the overdue ADR-104 re-measurement.
2. ✅ **Both knobs promoted**: `PSYCHE_DOMINANCE_CENTER=0.20`, `PSYCHE_PROACTIVE_JOY_PULSE=false` — as **code defaults** (`core/constants.py`) and on all six `.env` surfaces; prod container recreated (`docker compose up -d api` — `docker restart` does not re-read `env_file`) and runtime-verified.
3. ⏳ **After ≥ 14 days**, re-run with `--json-out after.json`; compare: distinct moods ≥ 7/14, top-mood share < 50%, D<0 share > 0% on calm exchanges, joy dominant share drops toward its appraisal-earned level, per-personality characteristic register preserved.

#### What the production baseline showed (2026-08-29)

The diagnosis held, and was **stronger than the simulation predicted**:

| | Simulated (v1.25.14) | Production measured |
|---|---|---|
| Dominance lock | D<0 never reached | **D<0 = 0.0%** — 769 snapshots, 3 users, 90 days |
| Joy pulse distortion | ~55% of turns | **31%** (90d) / **45.5%** (30d) main user; **93→100%** for a light user |
| Catalogue resting D | 0/14 below zero, mean +0.216 | **0/14 below zero**, live mean **+0.234** |

ADR-104's own scorecard, finally measurable: its **emotion-layer** fixes worked (pride 61% → 17.6%; dead emotions reachable; intensity ≥0.60 61.5% → 33.7%; co-active 4.52 → 3.4), its **mood-confinement** goal did not (still 4/14 moods, still 0% D<0 and 0% A<0).

Immediate effect of the promotion, measured on the live catalogue: **0/14 → 7/14** personalities rest D<0, D spread [+0.063, +0.494] → [−0.137, +0.294], mean +0.234 → **+0.034**, and `rasta` reaches `content` — a mood previously unreachable at rest. `antagonist` stays assertive at +0.294; `cynic` moves `determined` → `neutral`, the character-fidelity trade-off this ADR flagged.

#### Three findings the production data added

1. **Pride over-correction is now real** — 0% dominant over the last 30 days. ADR-104's own matrix has this row: *pride < 5% → F3 over-corrected → re-add a cooldowned pride pulse* (needs a `last_pride_pulse_at` column). Trigger met; not addressed here.
2. **Arousal is locked too, for a different reason.** The catalogue's A resting points already straddle zero (5/14 negative), yet production A<0 = 0.0%. That lock is **not** resting-point geometry — it is the appraisal stream never reporting low-arousal emotions (the F6 prompt layer). **This ADR does not fix it.**
3. **The golden guard pins the seeded catalogue, not the live one.** `antagonist` rests at D=+0.494 in production vs +0.243 in the seeding migration the guard freezes (no later migration touched it — a runtime edit). The guard is green while the live catalogue drifted, which also moved the derived center +0.216 → +0.234. The straddle property is guaranteed for the seeded catalogue only.

### Readjustment Decision Matrix

| Observation after data | Interpretation | Corrective |
|---|---|---|
| Assertive personalities lose their register (Cynic never `determined`) | center too strong for fidelity | 0.20 → 0.15, or add `pad_dominance_override` to the affected personality |
| D<0 still never visited | center too weak / appraisal never emits low-D emotions | raise center toward 0.25 max; else strengthen the F6 prompt (separate ADR) |
| Assistant reads flat/joyless after gate-off | joy pulse was masking a real appraisal gap | re-enable pulse; fix the self-report prompt instead |
| Golden test breaks on a legitimate future change | baseline dynamics intentionally changed | regenerate goldens IN the same PR with an ADR justification |

---

## Validation

- Golden characterization: 14/14 raw resting PADs frozen at center=0.0 (abs 1e-9) — proved the v1.25.14 merge inert, and now pins the mapping the 0.20 translation must not alter.
- Straddle at 0.20: 7/14 rest D < 0, ordering exactly preserved, P/A byte-identical.
- Oracle: 3 moods / 87% top → 5 moods / 40% top on the same scripted regime.
- Instrument: executed in `lia-api-dev` against the real dev DB; output confirmed the lock on live data (4/14 moods, 100% P+A+D+, stickiness 99.3%) and the catalogue mean +0.216.
- Suites: psyche domain 207/207; full lint + fast-unit gates green (see release notes).

## Related Decisions

- [ADR-104](ADR-104-Psyche-De-Saturation.md) — the corrective this instruments and completes; its §Validation re-measurement is now executable.
- [ADR-105](ADR-105-Psyche-Embodied-Expression.md) — expression layer; unaffected, measured separately.
- [ADR-068](ADR-068-Psyche-Engine.md) — the original engine.

## References

- kindalive (MIT, github.com/smithandrewjohn/kindalive) — analytical lens (equilibrium/headroom principle); mechanisms tested and rejected, no code imported.
- Mehrabian (1996) Big Five → PAD mapping; ALMA (Gebhard 2005).

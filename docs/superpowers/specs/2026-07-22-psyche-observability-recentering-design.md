# Psyche Engine — Observability First, Then Two Proven Fixes

**Date**: 2026-07-22
**Status**: APPROVED (user, 2026-07-22) — implemented, see ADR-142
**Follows**: ADR-068 (Psyche Engine), ADR-104 (De-Saturation), ADR-105 (Embodied Expression)
**ADR**: ADR-142 (Psyche Observability & Dominance Recentering)
**Trigger**: User question — can the kindalive project (github.com/smithandrewjohn/kindalive) enrich the Psyche Engine's relevance and naturalness?

---

## 1. Executive summary

The investigation started from kindalive and ended somewhere else. Kindalive's concrete
mechanisms (per-chemical half-lives, symmetric equilibrium) were **tested against our real
engine and rejected on measurement** — one is neutral here, the other is harmful. Its
*reading grid*, however (— "at rest, every axis must have headroom on both sides" —)
exposed a defect our own ADRs missed.

Deterministic replay of the real `PsycheEngine` (exact `service.py` wiring, 60 turns ×
4 regimes × the real 14-personality catalogue) established:

1. **The dominance axis is structurally off-center.** 0 of 14 personalities rest at
   D < 0 (spread +0.063 → +0.349). Five mood centroids require D < 0; they are
   unreachable in ordinary regimes. The personality named *Dépressif* (N=0.85,
   pleasure override −0.20) rests in mood `neutral`. ADR-104's damping is a
   *homothety* — it can never fix a *translation* problem.
2. **The proactive `joy` pulse falsifies the expressed emotion.** It fires 40/60 turns
   and makes `joy` the dominant emotion 55–58 % of turns, overriding what the LLM
   actually reported (measured: dominant even under a stream reporting only
   `determination`/`amusement`). ADR-104 removed the identical `pride` pulse (61 %
   dominance) and left this one in place.
3. **ADR-104's own acceptance criterion — production re-measurement after ≥ 1 month —
   is not tooled.** No measurement script exists. Every psyche correction so far has
   shipped without a way to verify its effect on real data. That absence, not any
   single parameter, is the root cause of the correction-upon-correction pattern.

**Decision**: ship the measurement instrument first, plus the two proven fixes strictly
disabled by default (merge = provable no-op), plus CI guards that make the desired
properties permanent. Look at real production numbers, then decide activation.

## 2. Evidence (deterministic, reproducible)

Replay harness: real `PsycheEngine` static methods, exact `process_pre_response` →
`process_post_response` call order and shipped defaults, scripted appraisal streams
(seeded RNG), no DB, no LLM.

### 2.1 Resting point of the real catalogue (damping 0.75, shipped)

| Axis | min | max | mean | Personalities resting < 0 |
|---|---|---|---|---|
| Pleasure | −0.090 | +0.332 | +0.128 | 3 / 14 |
| Arousal | −0.139 | +0.176 | +0.030 | 6 / 14 |
| **Dominance** | **+0.063** | **+0.349** | **+0.216** | **0 / 14** |

Distinct resting moods: **4 of 14** (`determined`, `neutral`, `playful`, `serene`).
Moods that are nobody's resting mood: the other 10, including every low-dominance one.

### 2.2 Simulation, Cynic, ordinary regime (60 turns, shipped config)

| Metric | Shipped | D recentered −0.20 |
|---|---|---|
| Distinct moods | 3 | **6** |
| Top-mood share | 93 % | **40 %** |
| min D over run | +0.261 | +0.061 |
| Mean PAD magnitude | 0.462 | 0.344 |

Order of personalities on the dominance axis under translation: **exactly preserved**
(verified on all 14). −0.28 over-corrects (mood count drops back); the optimum is a
tunable near −0.20 ⇒ `.env` setting, not a constant.

### 2.3 Proactive `joy` pulse (60 turns, ordinary regime)

| Metric | With pulse | Without pulse |
|---|---|---|
| `joy` pulse fired | 40 / 60 | — |
| `joy` dominant share | 55 % (Cynic) / 58 % (Friend) | `enthusiasm` 20 % |
| All mood metrics (moods, top-share, D_min, magnitude) | — | **identical to the hundredth** |

Removal is pure gain on emotion truthfulness, zero effect on mood dynamics.
Other pulses measured near-inert and legitimately scoped: `curiosity` fires only for
new relationships (`interaction_count < 5`), `enthusiasm` 1/60 with an anti-inflation
guard. Both are kept.

**Epistemic caveat (applies to §2.2–2.3, not §2.1)**: these magnitudes come from
*synthetic* appraisal streams. ADR-104 documents a synthetic-sim conclusion (F1)
that real-LLM testing later overturned — the same failure mode could bias these
numbers. The §2.1 resting-point facts and the ADR-104 production measurement
(`min_D = +0.368` over 3 months of real data) do **not** depend on the streams.
This is why production measurement (item 1) gates activation instead of these
simulated magnitudes.

### 2.4 Kindalive mechanisms, tested and rejected

| Mechanism | Result on our engine |
|---|---|
| Per-axis time constants (τ_A = 20 min, τ_P = 6 h, τ_D = 3 h) | Moods 3→3, D_min unchanged, magnitude slightly worse. In-burst the emotion push dominates any decay rate; between sessions both configs fully re-converge. **Rejected.** |
| Symmetric relaxation (strict equilibrium) | Moods 3→2, top-share 93→97 %. ADR-104's asymmetric choice was correct. **Rejected.** |
| Per-cause habituation (sliding window) | Nil under varied streams; −0.025 magnitude under repetitive streams. Real but second-order. **Deferred** pending production measurement. |
| Chemical substrate (8 chemicals under PAD) | Adds nothing the above does not, at the cost of a migration, 22 emotion signatures, and full re-validation. **Rejected.** |

## 3. Scope

### In scope

| # | Item | Behavior change when merged |
|---|---|---|
| 1 | `apps/api/scripts/measure_psyche.py` — production measurement instrument | None (read-only tool) |
| 2 | `PSYCHE_DOMINANCE_CENTER` setting + engine support | **None** (default 0.0 = today) |
| 3 | `PSYCHE_PROACTIVE_JOY_PULSE` setting + engine support | **None** (default true = today) |
| 4 | CI guards: catalogue-straddle + mood-reachability + no-op characterization | None (tests only) |
| 5 | Honesty micro-fixes (comments/docstrings only, see §7) | None |

### Out of scope (recorded, deliberately deferred)

- Activation of either setting in any `.env` — a separate decision after production
  measurement.
- Per-cause habituation, appraisal-prompt coherence fix (`determination`/
  `protectiveness` contradiction), continuous expression grammar (de-quantification),
  root recalibration of the Mehrabian mapping, `with_for_update()` on the psyche write
  path — all documented in §9 with their trigger conditions.
- Any change to the 14-mood / 22-emotion vocabulary, the API payload, or the frontend.
- Dropping the dead columns (`relationship_total_duration_minutes`, unread
  `triggered_at`) — needs a migration; bundled with the next psyche migration.
- Any code import from kindalive (MIT attribution burden for zero measured benefit).

## 4. Design

### 4.1 Measurement instrument — `apps/api/scripts/measure_psyche.py`

Read-only script that runs the ADR-104 metric battery against `psyche_history` /
`psyche_states` and prints a table + writes JSON (for diffing between runs):

- Per active user (≥ N `message` snapshots in window): distinct moods visited,
  top-mood share, octant coverage (% turns per P/A/D sign combination), dominant-emotion
  distribution (flagging `joy`/`pride` shares), emotion-intensity distribution
  (share ≥ 0.60), dominant-emotion stickiness, mean co-active emotions, resting
  magnitude after ≥ 12 h idle gaps.
- Global: per-personality resting-point classification (computed from the live
  `personalities` table, not the migration), catalogue D-spread.
- Connects through the app's own settings chain (`src.core.config`), with an explicit
  `--database-url` override for out-of-container runs; `--window-days` (default 30),
  `--min-snapshots` (default 20), `--json-out`.
- **Prod execution path — RESOLVED at implementation**: the script lives at
  `apps/api/scripts/measure_psyche.py` (not repo-root `scripts/audit/`) because
  `apps/api/Dockerfile.prod` does `COPY . .` from the `apps/api` build context, so
  `apps/api/scripts/` ships in the prod image while repo-root `scripts/` does not.
  Prod invocation: `docker exec lia-api-prod python scripts/measure_psyche.py`
  (validated against the dev container equivalent).
- English output, counters and aggregates only — **no message content, no PII** (INFO-level
  discipline per CLAUDE.md).

This is the missing artifact ADR-104 promised ("queries reproducible"). It also
becomes the before/after oracle for every future psyche change.

### 4.2 Dominance recentering — `PSYCHE_DOMINANCE_CENTER`

- `core/constants.py`: `PSYCHE_DOMINANCE_CENTER_DEFAULT: float = 0.0`.
- `core/config/psyche.py`: `psyche_dominance_center: float = Field(default=…, ge=0.0,
  le=0.5)` — translation subtracted from the dominance baseline; `0.0` disables
  (today's behavior). Recommended activation value 0.20 (derived: catalogue mean
  +0.216, validated in §2.2).
- `engine.py::compute_pad_baseline` gains `dominance_center: float = 0.0`, applied
  **after** the `PADOverride` blend and **after** damping, then clamped:
  `d_final = clamp(d_final * damping − dominance_center)`. Rationale: overrides express
  "assertive by design" (JARVIS +0.30, Trump +0.40); the translation shifts the whole
  frame while preserving their relative intent (verified: they stay on the assertive
  side, full ordering preserved).
- `service.py`: all **6** `compute_pad_baseline` call sites pass
  `dominance_center=settings.psyche_dominance_center`.
- `.env.example` + `.env.prod.example`: documented, value 0.0. (`.env.min.prod`
  carries no `PSYCHE_` vars — untouched.)

P and A are **not** recentered: measured spreads already straddle zero (§2.1).
A generic per-axis mechanism would be speculative config (YAGNI).

**Character-fidelity trade-off (explicit tuning criterion)**: at center 0.20 the
Cynic's ordinary-regime run no longer visits `determined` at all — it gains the
soft half of the space but loses part of its distinctive assertiveness, in tension
with ADR-104's "a Cynic *should* rest assertive". The activation decision must
therefore check, per personality, that its characteristic register survives; the
existing `pad_dominance_override` column (already used by JARVIS/Trump/Adolescent)
is the per-personality compensation mechanism if a character needs to keep an
assertive lean under a recentered frame. A gentler center (0.15) is the fallback
if fidelity loss is measured as too high.

### 4.3 Joy-pulse gate — `PSYCHE_PROACTIVE_JOY_PULSE`

- `core/constants.py`: `PSYCHE_PROACTIVE_JOY_PULSE_DEFAULT: bool = True`.
- `core/config/psyche.py`: `psyche_proactive_joy_pulse: bool` — when false, the joy
  pulse in `compute_proactive_emotions` is skipped (`curiosity` and `enthusiasm`
  pulses unaffected).
- `engine.py::compute_proactive_emotions` gains `joy_pulse_enabled: bool = True`
  (engine stays pure — no settings import); `service.py::process_pre_response` passes
  the setting.
- Docstring updated with the measured rationale (mirror of the ADR-104 pride note).
- Flag lifecycle: if production measurement confirms §2.3, the flag and the pulse are
  **removed outright** in the activation release (ADR-104 pride precedent) — this flag
  is a staging device, not a permanent switch.

### 4.4 CI guards (the "cannot silently regress" layer)

New test module `tests/unit/domains/psyche/test_mood_reachability.py`:

1. **No-op characterization**: `dominance_center=0.0` and `joy_pulse_enabled=True`
   reproduce today's values exactly (golden assertions on §2 numbers) — the formal
   proof that merging changes nothing.
2. **Catalogue-straddle guard**: loads the trait catalogue from the live source of
   truth used by the app (the migration data, imported via `importlib` from the
   versions file — no duplicated table), asserts that at the recommended center
   (0.20) the resting D-spread straddles zero (≥ 5 personalities each side) and that
   personality ordering is preserved under translation. Breaks CI if a 15th
   personality or a coefficient change re-locks the axis.
3. **Mood-reachability oracle**: the deterministic replay harness (promoted from the
   analysis scratchpad into the test, calling only real engine methods) asserts, on the
   scripted *ordinary-regime* Cynic run (the dominant production regime): center 0.20
   ⇒ ≥ 5 distinct moods with top-share ≤ 70 % (measured: 6 moods, 40 %); center 0.0
   ⇒ exactly the shipped 3-mood / 93 % outcome. This is the end-to-end oracle
   ADR-068/104 never had.

### 4.5 What is deliberately NOT built

No new module: the changes to `engine.py` are net-negative-to-neutral SLOC (a
parameter + one conditional + docstrings; file is frozen shrink-only at 874, currently
856 — headroom exists and the cap is respected). `service.py` (895/913) changes are
parameter threading only.

## 5. Edge cases

| Case | Handling |
|---|---|
| Personality with `pad_dominance_override` (3 exist) | Translation applied after blend — verified assertive-by-design stays relatively assertive; ordering preserved |
| `center > baseline` would push D below −1 | Final clamp already in `compute_pad_baseline`; setting bounded `le=0.5` |
| Existing users' stored mood far from new baseline on activation | No discontinuity: stored PAD is untouched; mood *decays* toward the shifted baseline at the normal decay rate (hours) — no visible jump |
| Soft/full reset while center active | Reset writes the *centered* baseline (all reset paths go through `compute_pad_baseline`) — consistent |
| Frontend readiness for newly reachable moods | Verified: `MOOD_COLORS` 14/14, `mood_to_color` 14/14, `psyche.moods` 14 keys × 6 locales, all 14 Noto WebP assets present (incl. `1f60a`, `1f61e`, `1f970`, `1f635`) |
| `build_psyche_prompt_block` (heartbeat/reminders/voice) | Same 6-call-site threading — proactive channels see the same centered baseline; no divergence |
| Measurement script on empty/small tables | `--min-snapshots` filter; prints "insufficient data" per user instead of NaN aggregates |
| Concurrent pre/post-response writes | Pre-existing race, unchanged by this work; documented in §9 (the `update()` docstring falsely claiming optimistic locking is corrected in §7) |

## 6. Acceptance criteria

- [ ] `task lint` + `task test:backend:unit:fast` green.
- [ ] Golden no-op test proves default config reproduces current behavior exactly.
- [ ] Catalogue guard + reachability oracle green at recommended values.
- [ ] `measure_psyche.py` runs against the dev DB and produces the full battery without
  touching message content; JSON output diffable.
- [ ] Zero frontend, zero migration, zero i18n change (verified by diff).
- [ ] Production measurement executed (RPi5, read-only) and numbers recorded **before**
  any activation decision — this closes ADR-104's open acceptance criterion.

Rollback: both settings revert instantly via `.env`; item 1/4/5 are inert.

## 7. Honesty micro-fixes (comment/docstring only, zero behavior)

Per the systemic rule "a docstring describing behavior the code does not have is a bug":

- `repository.py::update` — remove the false "(optimistic locking via updated_at)"
  claim; document the actual flush semantics and the known writer race.
- `models.py` — `trait_snapshot` comment says "Big Five trait values"; it stores
  emotions/relationship/drives/resonance. Fix the comment.
- `models.py` — traits comment "evolves independently" (they never evolve) and
  `narrative_identity` "generated monthly" (scheduler is weekly, sun@03:00). Fix both.

## 8. Consequences for the original question (kindalive)

Nothing is imported from kindalive — not the chemical substrate, not the code, not the
LLM-facing chemical interface. Its contribution is acknowledged in the future ADR as
the analytical lens ("rest must have headroom on both sides of every axis") that led to
the dominance-centering diagnosis. Its two transferable prompt-calibration lines
("under-reacting is as wrong as over-reacting"; "let opposite events land") are
deferred to the appraisal-prompt lot (§9), which must ship with a blind eval.

## 9. Deferred backlog (with trigger conditions)

| Item | Trigger to activate |
|---|---|
| Activate `PSYCHE_DOMINANCE_CENTER=0.20` in prod | Production measurement confirms D-locking on real data |
| Activate `PSYCHE_PROACTIVE_JOY_PULSE=false`, then delete pulse + flag | Production measurement confirms joy-dominance distortion |
| Per-cause habituation module | Post-activation measurement still shows repetitive-stream stickiness |
| Appraisal-prompt coherence (`determination`/`protectiveness` allowed on negative valence; kindalive calibration lines) | Own lot with blind eval (prompt changes are not unit-testable) |
| Continuous expression grammar (de-quantify PAD → voice) | After activation settles; blind eval protocol like ADR-105 |
| `with_for_update()` on psyche write path | Before any state-dependent feature (habituation) lands |
| Drop dead columns (migration) | Bundle with next psyche migration |
| Retire `PSYCHE_EMBODIED_INJECTION` legacy path (ADR-105 open item) | Same production-measurement campaign |

# Psyche Observability & Recentering — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline execution mandated by the user — no subagents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the psyche measurement instrument plus two proven fixes (dominance recentering, joy-pulse gate) — all inert at merge — with CI guards that make the desired properties permanent.

**Architecture:** Two new settings threaded from `PsycheSettings` into the pure `PsycheEngine` (which stays settings-free), a read-only measurement script inside the api build context, and a deterministic replay test module that pins today's behavior (golden no-op) and tomorrow's capability (reachability at the recommended center).

**Tech Stack:** Python 3.12, Pydantic Settings, SQLAlchemy 2 async, pytest (`asyncio_mode=auto`), structlog.

**Spec:** `docs/superpowers/specs/2026-07-22-psyche-observability-recentering-design.md`

## Global Constraints

- **Merge must be a provable no-op**: `PSYCHE_DOMINANCE_CENTER` defaults `0.0`, `PSYCHE_PROACTIVE_JOY_PULSE` defaults `true`; golden test proves defaults reproduce current behavior exactly.
- `engine.py` frozen at **874** logical SLOC (currently 856), `service.py` at **913** (currently 895) — shrink-only ratchet; verify with `scripts/audit/measure_sloc.py` after edits.
- Engine purity: `PsycheEngine` never imports `settings` — new behavior arrives as parameters with no-op defaults.
- No migration, no frontend change, no i18n change, no new dependency.
- **No git actions** — the user handles all commits.
- Measurement script: read-only, **no PII** (counters, IDs, emotion/mood names only), English output.
- Script placement: `apps/api/scripts/measure_psyche.py` — **decided**: `Dockerfile.prod` does `COPY . .` from the `apps/api` context, so `apps/api/scripts/` ships in the prod image (repo-root `scripts/` does not).
- Comments/docstrings in English; Google style; MyPy strict; Black line-length 100.
- Validation gates: `task lint` + `task test:backend:unit:fast` (backend), `task test:frontend` (prove zero frontend impact).

---

### Task 1: `PSYCHE_DOMINANCE_CENTER` — constants, settings, engine, service, `.env` surfaces

**Files:**
- Modify: `apps/api/src/core/constants.py` (PSYCHE block, ~line 3936)
- Modify: `apps/api/src/core/config/psyche.py`
- Modify: `apps/api/src/domains/psyche/engine.py:196-261` (`compute_pad_baseline`)
- Modify: `apps/api/src/domains/psyche/service.py` (6 call sites: lines ~173, 214, 256, 482, 995, 1296)
- Modify: `.env.example` (~line 1761), `.env.prod.example` (same block)
- Test: `apps/api/tests/unit/domains/psyche/test_engine.py` (class `TestComputePadBaseline`)

**Interfaces:**
- Produces: `compute_pad_baseline(traits, pad_override=None, damping=1.0, dominance_center=0.0) -> PADVector` — translation applied after override blend and damping: `d = clamp(d_final * damping - dominance_center)`.
- Produces: `settings.psyche_dominance_center: float` (ge=0.0, le=0.5, default 0.0).

- [ ] **Step 1: Write failing unit tests** in `TestComputePadBaseline`:

```python
def test_dominance_center_zero_is_noop(self):
    traits = PersonalityTraits(0.70, 0.55, 0.45, 0.25, 0.45)
    base = PsycheEngine.compute_pad_baseline(traits, damping=0.75)
    centered = PsycheEngine.compute_pad_baseline(traits, damping=0.75, dominance_center=0.0)
    assert centered == base

def test_dominance_center_translates_only_d(self):
    traits = PersonalityTraits(0.70, 0.55, 0.45, 0.25, 0.45)
    base = PsycheEngine.compute_pad_baseline(traits, damping=0.75)
    centered = PsycheEngine.compute_pad_baseline(traits, damping=0.75, dominance_center=0.20)
    assert centered.pleasure == base.pleasure
    assert centered.arousal == base.arousal
    assert centered.dominance == pytest.approx(base.dominance - 0.20)

def test_dominance_center_applies_after_override_blend(self):
    traits = PersonalityTraits()
    override = PADOverride(dominance=0.30)  # JARVIS-style assertive-by-design
    base = PsycheEngine.compute_pad_baseline(traits, override, damping=0.75)
    centered = PsycheEngine.compute_pad_baseline(traits, override, damping=0.75, dominance_center=0.20)
    assert centered.dominance == pytest.approx(base.dominance - 0.20)

def test_dominance_center_clamps_at_floor(self):
    traits = PersonalityTraits(0.0, 0.0, 0.0, 1.0, 1.0)  # lowest computed D
    centered = PsycheEngine.compute_pad_baseline(traits, damping=1.0, dominance_center=0.5)
    assert centered.dominance >= -1.0

def test_dominance_center_preserves_personality_ordering(self):
    catalogue = [...]  # the 14 trait/override tuples (same data as Task 3 loader)
    before = [PsycheEngine.compute_pad_baseline(t, o, damping=0.75).dominance for t, o in catalogue]
    after = [
        PsycheEngine.compute_pad_baseline(t, o, damping=0.75, dominance_center=0.20).dominance
        for t, o in catalogue
    ]
    assert sorted(range(14), key=lambda i: before[i]) == sorted(range(14), key=lambda i: after[i])
```

- [ ] **Step 2: Run — expect FAIL** (`TypeError: unexpected keyword argument 'dominance_center'`):
  `cd apps/api && .venv/Scripts/pytest tests/unit/domains/psyche/test_engine.py -k dominance_center -v`
- [ ] **Step 3: Implement** — `constants.py`: `PSYCHE_DOMINANCE_CENTER_DEFAULT: float = 0.0`; `config/psyche.py`: field with description; `engine.py`: parameter + translation line + docstring update; `service.py`: thread `dominance_center=settings.psyche_dominance_center` at the 6 call sites.
- [ ] **Step 4: Run — expect PASS**, then the full psyche suite:
  `.venv/Scripts/pytest tests/unit/domains/psyche/ -v` — all green, zero pre-existing failures introduced.
- [ ] **Step 5: `.env` surfaces** — add `PSYCHE_DOMINANCE_CENTER=0.0` with an activation comment to `.env.example` and `.env.prod.example` (`.env.min.prod` carries no PSYCHE vars — untouched).

### Task 2: `PSYCHE_PROACTIVE_JOY_PULSE` — gate the joy pulse

**Files:**
- Modify: `apps/api/src/core/constants.py`, `apps/api/src/core/config/psyche.py`
- Modify: `apps/api/src/domains/psyche/engine.py:1282-1347` (`compute_proactive_emotions`)
- Modify: `apps/api/src/domains/psyche/service.py` (`process_pre_response` call, ~line 318)
- Modify: `.env.example`, `.env.prod.example`
- Test: `apps/api/tests/unit/domains/psyche/test_engine.py` (proactive-emotions tests)

**Interfaces:**
- Produces: `compute_proactive_emotions(..., joy_pulse_enabled: bool = True) -> list[dict]`.
- Produces: `settings.psyche_proactive_joy_pulse: bool` (default True).

- [ ] **Step 1: Write failing tests**:

```python
def test_joy_pulse_enabled_by_default(self):
    pulses = PsycheEngine.compute_proactive_emotions(
        drive_curiosity=0.4, drive_engagement=0.8, interaction_count=100,
        last_appraisal={"quality": 0.8}, self_efficacy=None,
        existing_emotions=[], now_iso="2026-01-01T00:00:00+00:00",
    )
    assert any(p["name"] == "joy" for p in pulses)

def test_joy_pulse_gated_off(self):
    pulses = PsycheEngine.compute_proactive_emotions(
        drive_curiosity=0.4, drive_engagement=0.8, interaction_count=100,
        last_appraisal={"quality": 0.8}, self_efficacy=None,
        existing_emotions=[], now_iso="2026-01-01T00:00:00+00:00",
        joy_pulse_enabled=False,
    )
    assert not any(p["name"] == "joy" for p in pulses)

def test_joy_gate_leaves_other_pulses_untouched(self):
    pulses = PsycheEngine.compute_proactive_emotions(
        drive_curiosity=0.8, drive_engagement=0.9, interaction_count=2,
        last_appraisal={"quality": 0.9}, self_efficacy=None,
        existing_emotions=[], now_iso="2026-01-01T00:00:00+00:00",
        joy_pulse_enabled=False,
    )
    names = {p["name"] for p in pulses}
    assert "curiosity" in names and "enthusiasm" in names and "joy" not in names
```

- [ ] **Step 2: Run — expect FAIL** on the keyword; **Step 3: Implement** (guard the joy block with `joy_pulse_enabled and ...`; docstring gets the measured rationale mirroring the pride note; service passes the setting); **Step 4: Run — PASS + full psyche suite**; **Step 5: `.env` surfaces** (`PSYCHE_PROACTIVE_JOY_PULSE=true`).

### Task 3: CI guards — `test_mood_reachability.py`

**Files:**
- Create: `apps/api/tests/unit/domains/psyche/test_mood_reachability.py`

**Interfaces:**
- Consumes: Task 1's `dominance_center` kwarg; migration data `PERSONALITY_TRAITS` loaded via `importlib.util.spec_from_file_location` from `apps/api/alembic/versions/2026_04_01_0003-assign_big_five_traits_to_personalities.py` (path = `Path(__file__).parents[4] / "alembic" / "versions" / ...`) — **no duplicated table**.

Content (three guard families, `pytestmark = pytest.mark.unit`):

1. **Golden no-op characterization** — resting PAD of all 14 catalogue personalities at shipped damping with default center equals frozen literals (generated once by running the real function; `pytest.approx(..., abs=1e-9)`). Failure message: "psyche baseline dynamics changed — if intended, regenerate goldens and justify in the ADR".
2. **Catalogue-straddle guard** — at recommended center **0.20**: ≥ 5 personalities rest `D < 0`, ≥ 5 rest `D > 0`, and dominance **ordering is exactly preserved** vs center 0.0.
3. **Reachability oracle** — a fixed literal ordinary-regime stream (~30 turns: bursts of 6 messages 3 min apart, 16 h session gaps — the `_simulate` pattern of `test_desaturation.py` extended with per-turn `dt`), Cynic traits: center 0.0 ⇒ ≤ 4 distinct moods (today's lock), center 0.20 ⇒ ≥ 5 distinct moods and top-mood share ≤ 70 %.

- [ ] Step 1: generate golden literals (one-shot script run via `.venv/Scripts/python -c`), Step 2: write the module with the three families, Step 3: run — all green with center values proving both arms, Step 4: full psyche suite green.

### Task 4: `apps/api/scripts/measure_psyche.py` — the measurement instrument

**Files:**
- Create: `apps/api/scripts/measure_psyche.py`
- Test: `apps/api/tests/unit/domains/psyche/test_measure_psyche.py` (pure aggregation functions only)

**Interfaces:**
- Consumes: `PsycheHistory`, `PsycheState`, `Personality`, `User` models; `PsycheEngine.classify_mood` / `compute_pad_baseline`; app settings chain.
- CLI: `--window-days 30 --min-snapshots 20 --json-out PATH --database-url URL`.

Design: thin async I/O shell (fetch rows) + **pure aggregation functions** (unit-tested without DB):
`aggregate_user_metrics(snapshots: list[SnapshotRow]) -> UserMetrics` computing — distinct moods visited (labels recomputed via `classify_mood`), top-mood share, octant coverage, dominant-emotion distribution (`joy`/`pride` shares flagged), intensity ≥ 0.60 share, dominant-emotion stickiness, mean co-active emotions, post-first-message magnitude after ≥ 12 h idle (named exactly that — snapshots are post-appraisal, not resting).
`classify_catalogue(personalities, damping, center) -> list[RestingRow]` for the per-personality resting table + D-spread.
Output: human table (stdout) + `--json-out` diffable JSON. Read-only session; `--min-snapshots` filter prints "insufficient data" per user instead of NaN.

- [ ] Step 1: failing tests for the pure aggregators (stickiness, octants, idle-gap magnitude, empty input), Step 2: implement aggregators, Step 3: implement CLI shell + queries, Step 4: run against dev DB (docker) and verify output + JSON, Step 5: full psyche suite green.

### Task 5: Honesty micro-fixes (comments/docstrings only — zero behavior)

**Files:**
- Modify: `apps/api/src/domains/psyche/repository.py:78` — drop the false "(optimistic locking via updated_at)"; document flush semantics + known writer race.
- Modify: `apps/api/src/domains/psyche/models.py` — `trait_snapshot` comment (actually stores emotions/relationship/drives/resonance), traits header "evolves independently" (they do not), `narrative_identity` "monthly" → weekly (sun@03:00).

- [ ] Single step: apply the four comment corrections; run psyche suite (no behavior — still green).

### Task 6: Documentation

**Files:**
- Create: `docs/architecture/ADR-142-Psyche-Observability-And-Dominance-Recentering.md` (context = §1-2 of the spec; decision; kindalive acknowledged as analytical lens, mechanisms tested-and-rejected; readjustment matrix; flags lifecycle).
- Modify: `docs/architecture/ADR_INDEX.md` (ADR-142 entry after ADR-141, same format).
- Modify: spec `2026-07-22-psyche-observability-recentering-design.md` — §4.1 open decision → resolved (`apps/api/scripts/`, Dockerfile evidence); status DRAFT → APPROVED (user 2026-07-22).
- Check: `docs/INDEX.md` for any pointer that must change.

- [ ] Single step: write ADR-142, index entry, spec update.

### Task 7: Full verification (fresh evidence)

- [ ] `cd apps/api && .venv/Scripts/pytest tests/unit/domains/psyche/ -v` — full domain suite.
- [ ] `task lint` — Black + Ruff + MyPy strict + frontend linters, clean.
- [ ] `task test:backend:unit:fast` — full fast unit gate, clean.
- [ ] `.venv/Scripts/python ../../scripts/audit/measure_sloc.py src/domains/psyche` — engine ≤ 874, service ≤ 913.
- [ ] `task test:frontend` — proves zero frontend impact (no file under `apps/web` touched; suite must stay green).
- [ ] Diff review: zero migration, zero i18n, zero frontend file in the diff.

## Self-Review (done at write time)

- Spec coverage: §4.1→Task 4, §4.2→Task 1, §4.3→Task 2, §4.4→Task 3, §7→Task 5, §6 gates→Task 7, §4.1 placement decision + ADR→Task 6. No gaps.
- No placeholders: golden literals and the literal stream are produced by explicit generation steps within their tasks.
- Type consistency: `dominance_center: float = 0.0` and `joy_pulse_enabled: bool = True` used identically across Tasks 1-4.

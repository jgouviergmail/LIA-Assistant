# Design — Interests "Dormant" Visibility & Memory Purge-Risk Exposure

- **Date:** 2026-05-21
- **Status:** Approved (design), pending implementation plan
- **Scope:** Two related user-control gaps in the auto-decay lifecycle of `domains/interests` and `domains/memories`.
- **Migration required:** None (all needed columns already exist).

---

## 1. Context & Problem

Both the Interests and Memories domains run a daily background job that automatically
demotes/removes low-value items. Investigation revealed two distinct user-control gaps.

### 1.1 Interests — dormant items become invisible and uncontrollable

The daily `cleanup_interests` job (`infrastructure/scheduler/interest_cleanup.py`)
flips an interest to `status = "dormant"` when its effective weight stays below `0.5`
and it has not been mentioned for `interest_dormant_threshold_days` (15 days in prod).
Dormant interests are then auto-deleted after `interest_deletion_threshold_days` (90 days).

The backend `GET /interests` returns **all** interests regardless of status
(`get_all_for_user` applies no status filter), but the frontend
`InterestsSettings.tsx` only renders two buckets:

- `groupedByCategory` → `status === "active"`
- `blockedInterests` → `status === "blocked"`

`status === "dormant"` is filtered nowhere, so dormant interests are **invisible** in the
UI. The user cannot edit, delete, or otherwise act on them, yet they are still counted in
the `total` shown in the stats bar (counter inconsistency), and they are silently deleted
after 90 days.

### 1.2 Memories — purge risk is invisible; deletion is silent and irreversible

The daily `cleanup_memories` job (`infrastructure/scheduler/memory_cleanup.py`)
performs a **hard delete** of any memory whose retention score
(`weight_importance * importance + weight_recency * recency_factor`, minus a zero-usage
penalty) falls below `memory_purge_threshold`, unless it is `pinned` or still within the
grace period (`memory_min_age_for_cleanup_days`).

Unlike Interests, the user **does** keep control: all memories stay visible
(`GET /memories` returns everything, category filter aside), and the user can pin a memory
(`PATCH /memories/{id}/pin`) to protect it permanently. The gap is different: the user has
**no visibility into purge risk**. The `retention_score` is never surfaced, so the user has
no signal telling them a memory is about to disappear and should be pinned. The deletion is
silent and irreversible.

---

## 2. Goals / Non-Goals

### Goals

- **Interests:** make dormant interests visible in a dedicated, visually distinct section
  with full edit/delete control and an explicit **Reactivate** action; fix the counter.
- **Memories:** surface purge risk (read-only) so the user can decide to pin in time.

### Non-Goals

- No change to the purge/dormancy *mechanisms* themselves (thresholds, schedules, decay).
- No soft-delete / trash / recovery for memories (explicitly deferred).
- No `pinned` mechanism added to Interests (deferred; not needed for this scope).
- No notification/alert pipeline before purge.
- No unrelated refactoring (e.g. extracting the hardcoded `0.5` dormancy threshold — not
  load-bearing for this design since Reactivate resets rather than compares).

---

## 3. Design — Subject 1: Interests "Dormant" Section

### 3.1 Backend

**Expose the dormant count** — `schemas.py`:

- Add `dormant_count: int` to `InterestListResponse`.
- In `router.list_interests`, compute it alongside the existing `active_count` /
  `blocked_count` (data is already returned by `get_all_for_user`).

**Reactivate (reset to "fresh")** — the chosen semantics is "treat as a brand-new interest":

- New repository method `InterestRepository.reactivate(interest, now=None)` that mirrors the
  initial state set by `create()`:
  - `positive_signals = 1`
  - `negative_signals = 0`
  - `status = InterestStatus.ACTIVE.value`
  - `last_mentioned_at = now`
  - `dormant_since = None`
  - `last_notified_at = None` (mirror a new interest → eligible for notification again)
  - `topic`, `category`, `embedding` left untouched.
- DRY note: the initial signal values (`1`, `0`) are currently inlined in `create()`. Extract
  shared constants (`INTEREST_INITIAL_POSITIVE_SIGNALS`, `INTEREST_INITIAL_NEGATIVE_SIGNALS`)
  in `core/constants.py` and reference them from both `create()` and `reactivate()`.
- Rationale: with default Bayesian priors (2, 1) and fresh `last_mentioned_at`, the effective
  weight resets to ~0.75 (> 0.5), so the next nightly run will not immediately re-dormant it.
  This also sidesteps the temporal-decay dead zone (an old dormant cannot exceed the threshold
  through signals alone because decay caps the effective weight).

**New endpoint** — `router.py`:

- `POST /interests/{interest_id}/reactivate` → returns `InterestResponse`.
- Ownership guard identical to `delete_interest` / `update_interest`
  (`interest.user_id != user.id` → `raise_interest_not_found`).
- **Status guard:** valid only when `status == "dormant"`. On any other status, return
  `409 Conflict` (`ResourceConflictError`) — defensive: the UI only exposes the button in the
  dormant section, but the endpoint must not silently reset an `active` interest's history or
  un-block a `blocked` one.
- Calls `repo.reactivate(interest)`, commits, returns `_interest_to_response`.
- Structured log `interest_reactivated` (user_id, interest_id).

**Trade-off (assumed):** reset-to-fresh discards the accumulated `positive_signals` /
`negative_signals` history. `topic`, `category`, and `embedding` are preserved. The alternative
(preserve signals + only refresh `last_mentioned_at`) was rejected: it fails for interests with
a strong negative history (base weight would stay below the threshold even with decay reset), so
the full reset is the only approach that guarantees reactivation in all cases.

**Editing a dormant interest stays status-neutral**: `update_interest` does not change status.
Reactivation is the only explicit path back to `active`. (A dormant interest whose signals are
edited may show a higher weight % while still labelled "dormant" — acceptable, and the explicit
Reactivate button is the intended path.)

### 3.2 Frontend

`hooks/useInterests.ts`:

- Expose `dormantCount` from the response.
- Add `reactivateInterest(interestId)` mutation (`POST /interests/{id}/reactivate`) with an
  optimistic update: set `status → "active"` locally and recompute `active_count` /
  `dormant_count`.

`components/settings/InterestsSettings.tsx`:

- Compute `dormantInterests = sortedInterests.filter(i => i.status === "dormant")`
  (mirror of `blockedInterests`).
- New `<AccordionItem value="dormant">` placed **between** the active category sections and the
  "Blocked" section.
- Visual treatment: reduced opacity + a "Dormant" badge with a `Moon` (lucide) icon. **No**
  `line-through` (dormant items are reactivable, not revoked — distinct from blocked).
- Per-item actions: **Reactivate** (`RotateCcw`/`Sparkles` icon), Edit, Delete — same desktop
  hover controls and mobile action popup pattern as active items.
- Stats bar: replace "X interests (Y blocked)" with a breakdown
  **"X active · Y dormant · Z blocked"** using the now-available three counters.

### 3.3 i18n (6 languages: en, fr, de, es, it, zh)

New `interests.*` keys: `dormant_section`, `dormant_badge`, `reactivate`,
`reactivate_success`, `reactivate_error`, plus counter labels (`active`, `dormant`).
Strict `en` parity enforced by pre-commit; zh duplicates plural forms per CLDR.

---

## 4. Design — Subject 2: Memory Purge-Risk Exposure

### 4.1 Backend — centralize retention logic (Boy Scout)

`calculate_retention_score` and `should_purge` currently live in
`infrastructure/scheduler/memory_cleanup.py` (infrastructure layer). Calling them from the
router (domain layer) would invert the dependency direction.

- **New module `src/domains/memories/retention.py`** holding the pure (I/O-free) functions:
  - `calculate_retention_score(...)` — moved **verbatim**, signature unchanged.
  - `should_purge(...)` — moved **verbatim**, signature unchanged (including its short-circuit
    that returns score `1.0` for pinned / grace-period memories — relied on by the scheduler).
  - `classify_purge_risk(memory, now, config) -> PurgeRisk` — new (see 4.2).
- **No "unified evaluation" function.** An earlier idea to merge `should_purge` + `classify`
  was dropped: `should_purge`'s `1.0` short-circuit is behavior the scheduler tests assert, so
  fusing them would risk a regression. The three functions stay separate and share only
  `calculate_retention_score`.
- `memory_cleanup.py` imports these from the domain module (infrastructure → domain, correct
  direction). **No behavioral change to the job** — pure import refactor.
- **Test impact (must preserve calibration):** `tests/unit/infrastructure/scheduler/test_memory_cleanup.py`
  currently imports `calculate_retention_score` / `should_purge` from the scheduler. The pure-function
  tests move to a new `tests/unit/domains/memories/test_retention.py` (imports updated to
  `domains.memories.retention`), keeping their assertions **identical** (e.g. "importance=0.5 @ 30
  days is purged"). `test_memory_cleanup.py` keeps only the orchestrator-job test.
- A small frozen `RetentionConfig` dataclass groups the seven retention settings, built once
  from `settings` per request and passed to the pure functions (keeps them testable and avoids
  re-reading `settings` per memory).

### 4.2 Backend — enrich the response (read-only, on-the-fly)

`schemas.py` — add to `MemoryResponse`:

- `retention_score: float | None` — computed score (None only if not computable).
- `purge_risk: Literal["protected", "safe", "at_risk", "imminent"]`.

`classify_purge_risk` computes the **real** score once via `calculate_retention_score` (it does
**not** call `should_purge`, to avoid the `1.0` short-circuit), then applies the 4-state logic.
The score it computes is the value exposed as `retention_score`. The minor inlining of the
grace/threshold comparison (also present in `should_purge`) is accepted to keep `should_purge`
untouched for the scheduler.

States (evaluated in order):

- `protected` → `memory.pinned` is True (never auto-purged by user choice).
- `safe` (grace) → not pinned **and** `age_days < memory_min_age_for_cleanup_days`
  (not yet eligible). See trade-off below.
- `imminent` → eligible and `retention_score < memory_purge_threshold`
  (would be deleted on the next nightly run).
- `at_risk` → eligible and `memory_purge_threshold ≤ retention_score < memory_purge_threshold
  + memory_purge_at_risk_margin` (close to the threshold).
- `safe` → eligible and `retention_score ≥ memory_purge_threshold + memory_purge_at_risk_margin`.

**Trade-off (assumed):** a young, low-score memory shows `safe` during the grace period, then
flips to `imminent` once the grace elapses. This is deliberate — the grace period exists to give
recent content time, and flagging just-created memories as "at risk" would be alarmist. The user
can still pin at any time.

`router._memory_to_response` becomes `_memory_to_response(memory, now, config)`:

- Builds nothing per-call beyond the arithmetic; `now` and `config` are created once per request
  handler and threaded into each conversion (list / get / create / update / export).
- Cost: O(n) pure arithmetic over ≤200 in-memory objects, **no additional DB query**.

### 4.3 Settings / constants (parameterizable, not inlined)

- `core/constants.py`: `MEMORY_PURGE_AT_RISK_MARGIN_DEFAULT = 0.1`.
- `core/config/agents.py`: `memory_purge_at_risk_margin: float = Field(default=..., ge=0.0, le=1.0)`
  with description.
- `.env.example` and `.env.prod.example`: add `MEMORY_PURGE_AT_RISK_MARGIN`.

### 4.4 Frontend

`hooks/useMemories.ts` — extend the `Memory` interface with
`retention_score?: number` and `purge_risk?: 'protected' | 'safe' | 'at_risk' | 'imminent'`.

`components/settings/MemorySettings.tsx`:

- On cards where `purge_risk === 'at_risk'` or `'imminent'`: an amber `AlertTriangle` badge with
  a tooltip — "This memory may be forgotten — pin it to keep it." `imminent` uses a stronger
  (e.g. red) emphasis than `at_risk`.
- The existing Pin button is the natural mitigation; emphasize it on at-risk/imminent items.
- Optional (low priority): a section-header summary "N memories may be forgotten."

### 4.5 i18n (6 languages)

New `memories.*` keys: `purge_risk_badge_at_risk`, `purge_risk_badge_imminent`,
`purge_risk_tooltip`, `purge_risk_summary`. Strict `en` parity; zh CLDR plural duplication.

---

## 5. Data Model

No migration. Reused as-is:

- Interests: `status`, `dormant_since`, `positive_signals`, `negative_signals`,
  `last_mentioned_at`, `last_notified_at`.
- Memories: `importance`, `usage_count`, `created_at`, `pinned`.

---

## 6. Testing

- **Backend unit:**
  - `InterestRepository.reactivate` resets all counters/timestamps to the "fresh" state.
  - `retention.classify_purge_risk` returns the correct state for each branch
    (pinned → protected; grace period → safe; below threshold → imminent;
    within margin band → at_risk; above → safe). Read thresholds from `settings`, never hardcode.
  - Reactivate endpoint: ownership guard (404 on foreign interest), status guard (409 on a
    non-dormant interest), happy path (dormant → active with fresh counters).
- **Frontend (vitest):**
  - Dormant section renders dormant interests and the Reactivate action.
  - Risk badge renders for `at_risk` / `imminent`, absent for `safe` / `protected`.
- Tests mirror source structure; pytest markers (`unit`), `asyncio_mode = "auto"`.

---

## 7. Documentation

- Update the technical docs of both domains (Interests lifecycle: add dormant visibility +
  reactivation; Memories: document purge-risk exposure and the new margin setting).
- **No ADR** — this is a UX/observability improvement, not an architectural decision.
- Update `docs/INDEX.md` cross-references if the touched technical docs change titles.

---

## 8. Observability

- Structured log `interest_reactivated` (user_id, interest_id).
- No new Prometheus metric deemed necessary (reactivation is low-frequency, user-driven).

---

## 9. Files Touched (summary)

### Subject 1 — Interests

- `apps/api/src/domains/interests/schemas.py` — `dormant_count` on `InterestListResponse`.
- `apps/api/src/domains/interests/repository.py` — `reactivate()` method.
- `apps/api/src/domains/interests/router.py` — compute `dormant_count`; `POST /{id}/reactivate`.
- `apps/api/src/core/constants.py` — `INTEREST_INITIAL_POSITIVE_SIGNALS` / `_NEGATIVE_SIGNALS`.
- `apps/web/src/hooks/useInterests.ts` — `dormantCount`, `reactivateInterest()`.
- `apps/web/src/components/settings/InterestsSettings.tsx` — dormant section, reactivate, counter.
- `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — `interests.*` keys.

### Subject 2 — Memories

- `apps/api/src/domains/memories/retention.py` — **new** pure module (score, should_purge, classify).
- `apps/api/src/infrastructure/scheduler/memory_cleanup.py` — import from `retention.py`.
- `apps/api/src/domains/memories/schemas.py` — `retention_score`, `purge_risk` on `MemoryResponse`.
- `apps/api/src/domains/memories/router.py` — risk computed in `_memory_to_response`.
- `apps/api/src/core/constants.py` — `MEMORY_PURGE_AT_RISK_MARGIN_DEFAULT`.
- `apps/api/src/core/config/agents.py` — `memory_purge_at_risk_margin` setting.
- `.env.example`, `.env.prod.example` — `MEMORY_PURGE_AT_RISK_MARGIN`.
- `apps/web/src/hooks/useMemories.ts` — `Memory` type fields.
- `apps/web/src/components/settings/MemorySettings.tsx` — risk badge/tooltip.
- `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — `memories.*` keys.

---

## 10. Non-Regression Guarantees & Validation

These features are **comfort/UX additions**: the hard requirement is **zero regression** on
existing behavior. The design is therefore strictly additive.

### 10.1 Guarantees (by construction)

- **API backward compatibility:** new response fields (`dormant_count`, `retention_score`,
  `purge_risk`) are **added** with defaults. Existing clients ignore unknown fields; no field is
  removed, renamed, or retyped. No existing endpoint signature changes.
- **New endpoint only:** `POST /interests/{id}/reactivate` is additive. `list` / `create` /
  `update` / `delete` / `feedback` keep identical behavior (interests `update` stays
  status-neutral).
- **Scheduler behavior frozen:** moving `calculate_retention_score` / `should_purge` to
  `retention.py` is a pure import refactor; signatures and logic are unchanged, so
  `cleanup_memories` and `cleanup_interests` behave identically. The dormancy/purge thresholds,
  schedules, and decay are untouched.
- **Existing tests stay green with identical assertions:** only the *imports* of the moved
  functions change; the calibration assertions (e.g. "importance=0.5 @ 30 days is purged")
  remain byte-for-byte. No existing test assertion is weakened or deleted.
- **No DB migration:** existing rows are never read or written differently; reused columns only.
- **Frontend additive:** the "Dormant" section and the risk badge are new render branches; the
  active/blocked sections and the memory cards' existing behavior are unchanged (the interests
  counter only changes its label text).
- **i18n additive:** keys are added under existing namespaces; strict `en` parity preserved.

### 10.2 Validation strategy (via Docker, never local)

- Run the existing backend unit + agents suites **before** (baseline) and **after** the change;
  both must pass with no modified assertions: `task test:backend:unit:fast`,
  `task test:backend:agents`.
- Run the existing frontend suite (`task test:frontend`); must stay green.
- New tests added (interests `reactivate`, `retention.classify_purge_risk`, reactivate endpoint
  guard) must read thresholds from `settings`, never hardcode.
- **Verify Docker app startup** after the change (config composition, router wiring, scheduler
  registration) — linters + unit tests are not sufficient on their own.
- `task pre-commit` (format + lint + fast unit + i18n parity) must pass clean (no `--no-verify`).

## 11. Decision Log

1. Interests dormant items → dedicated visible "Dormant" section (not pinned-style protection).
2. Reactivation → explicit button that **resets counters to fresh** (not auto-via-signals, which
   the temporal-decay cap would block for old dormants). Accepts loss of signal history; topic /
   category / embedding preserved.
3. `reactivate` is valid only on `dormant` interests → `409 Conflict` otherwise.
4. Editing a dormant interest is status-neutral.
5. Memory purge risk → 4 states (`protected` / `safe` / `at_risk` / `imminent`); young low-score
   memories show `safe` during the grace period (deliberate, non-alarmist).
6. Retention score → recomputed on the fly (negligible cost, always fresh, no migration, no
   staleness vs. importance edits), logic centralized in `retention.py`; `should_purge` /
   `calculate_retention_score` kept intact (no unified function) to protect scheduler calibration.
7. No DB migration; no ADR; no soft-delete/trash; no `pinned` for interests.
8. **Comfort features → zero regression**: strictly additive, existing behavior and test
   assertions frozen (§10).

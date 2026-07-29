# UX Actions Program — Verified Design & Multi-Lot Roadmap

**Date:** 2026-07-28 (arbitrations) / 2026-07-29 (implemented) · **Status:** ✅ ALL 7
LOTS IMPLEMENTED + FULL GATES GREEN 2026-07-29 — **NOT COMMITTED** (awaiting user go).
**Baseline:** HEAD `87f102f4` (v1.25.33 + `/more` page).
**Scope:** 10 evolutions in 7 lots — A (R01+K01+N-13+SLASH), B (D-04), C (QW-24),
D (C-02), E (T01), F (N-07), G (N-09). ADRs 173→176 added.

**Final gate evidence (2026-07-29):** `task ci:fast` exit 0 (lint, mypy strict, CC
back+front ratchets, a11y, react-hooks, i18n parity ×6, docs, lockfiles, ci-parity,
frontend coverage 67.99 %, deploy tests 51/0) · frontend **4027/4027** · backend fast
**14734 passed** / 10 skipped · `db:migrate:replay-check` OK (4 new migrations) ·
targeted e2e **37/37** (header reachability ×locales, mobile-nav, deep-links, search,
chat header/composer).

Every claim below was verified in-code on 2026-07-28/29 (file:line evidence in the
conversation that produced this doc). Sibling program docs (same format):
`2026-07-22-ux-refinements-program.md`, `2026-07-21-quick-wins-ux-program.md`.

---

## Session protocol (resume ritual)

1. Read this doc top to bottom; the **status tracker** (bottom) says where the program
   stands. Check `git log --oneline -5` + `git status`; if HEAD moved past the baseline,
   re-verify the target lot's volatile anchors before coding.
2. Implement **inline** (user rule: no subagents), TDD, following root + `apps/web`
   CLAUDE.md. Autonomous chaining across lots is authorized — stop ONLY for an
   arbitration/precision the user must give.
3. Per-lot gates (list per lot below) + full self code-review before declaring a lot
   done. Evidence before assertions. Runtime proof happens in the Docker dev containers
   (`docker restart lia-web-dev` first — host edits do NOT hot-reload; API is HTTPS on
   :8000, `curl -sk`).
4. Update the status tracker here + memory after each lot. **Never commit/push — the
   user does.**
5. Raise coverage/ratchet floors only per the standing rules (≥2 pts margin; frontend
   floors NOT before 67/68 per memory `project_ux_polish_program_2026_07_28`).

---

## Decided arbitrations (user sign-off 2026-07-28)

| # | Decision |
|---|----------|
| A1 | **QW-24 card actions auto-send** through the chat pipeline via a NEW `?intent=` deep-link param (consume-once, stripped from URL BEFORE sending, StrictMode-idempotent). `?draft=` keeps its never-auto-send semantics (A4 contract amended by a short ADR: `draft` = prefill, `intent` = execute). Guards: usage-blocked / isTyping / pending HITL ⇒ degrade to prefill. External writes stay protected by the existing tool-level HITL (task writes are draft-gated: `hitl_classifier.py:654-660`). |
| A2 | **C-02 mobile surface = home-made bottom sheet** on the existing Radix Dialog dependency (no `vaul`). Desktop = selection-anchored popover. Selected text is captured AT SHEET/POPOVER OPEN TIME (iOS clears selection on sheet tap). |
| A3 | **N-07 phase 1 = "time + condition"**: triggers stay cron-shaped; new `trigger_kind`, `condition_config` (JSONB), `condition_state` (dedup ledger), `requires_approval`. Condition evaluators run at fire time, reuse briefing fetcher caches for provider-backed conditions, and dedup on a fingerprint. True event-driven (Gmail watch/PubSub) is a separate phase 2, out of this program. NO guard on `SCHEDULED_ACTIONS_ENABLED` (the flag does not exist — documented trap). |
| A4 | **N-09 v1 = read-only aggregation** following the `domains/briefing/` pattern (per-fetcher own session, per-section Redis cache, split endpoints). Identity resolution v1 = provider contact + exact-email then normalized-name matching, displayed as best-effort. No new table until value is proven. |
| A5 | **N-13 honest scope**: PWA manifest shortcuts (×6 locales) + `?voice=1` chat affordance + fix stale spaces shortcut. Native home-screen widgets are impossible for PWAs on Android/iOS — out of scope, recorded here. |

Recorded micro-decisions (do not re-litigate; flag only if evidence invalidates them):

- **T01 [CORRECTED]**: rich debrief fields extend **`ReturnProposal`** (our synthesis LLM
  output), NOT `StructuredCallData` (extracted from the ElevenLabs payload). Debrief is
  persisted in a new JSONB `debrief` on `PhoneCall` (conscious D-8 extension, own ADR) so
  `TelephonyCallsSection` can re-display it after a missed notification.
- **N-13 [ADAPTED 2026-07-29]**: v1.25.33 shipped hold-to-speak PTT on the composer
  button. `?voice=1` therefore does NOT auto-record (hold gesture + mic permission
  semantics); it highlights/focuses the voice affordance in the chat.
- **D-04**: `last_good` stale cache must never resurrect a `hidden` section (the hidden
  short-circuit at `briefing/service.py:397-401` stays first); purge `last_good` on
  connector disconnect; per-card retry must NOT regenerate greeting+synthesis (cards-only
  refresh path).
- **QW-24**: verify `complete_task`'s HITL classification during Lot C before wiring
  "Terminé" (expected: task_update draft).
- **SLASH admin**: user shortcuts live in a `chat_shortcuts` JSONB on `users` (new-dict
  rule, tolerant reader like `sanitize_briefing_preferences`, count cap from settings);
  merged as statics + user + skills with a reserved prefix to make id collisions
  impossible by construction.
- **R01**: desktop nav currently hardcodes 4 links while `dashboard-nav.ts` claims to be
  the single table both surfaces render — docstring/code contradiction (systemic rule):
  fix by making the desktop nav render from `DASHBOARD_DESTINATIONS` (icon map keyed by
  segment). If `dashboard-header-reachability` e2e rejects 5 labeled destinations at
  768–1024 px, plan B = compact icon entry, documented here.

---

## Completion matrix (partial features: existing → gap → done-when)

| Feature | Existing (verified) | Completion | Done when |
|---|---|---|---|
| QW-9→QW-24 | 7 cards deep-link prefilled chat (`chatDraftHref`), `?draft=` consumed+stripped | `?intent=` route via `sendMessageFromPresent` (the W3-retry path), per-card action buttons, fallback to prefill on guards, ADR amending A4 | every action executes or degrades; HITL of task completion verified; unit+e2e; i18n ×6 |
| D-04 | `UpdatedAtBadge` (30 s), per-card refresh, error CTA per `error_code`, 5 statuses | additive `from_cache`/`last_attempt_at`/`stale_generated_at` (Pydantic + TS mirrors), `last_good` Redis key (long TTL), stale-with-error rendering, LLM-free per-card retry | connector outage shows stale data + last attempt + retry w/o LLM; schema round-trip tested; 4 statuses × (with/without stale) covered |
| T01 | tool-less synthesis, `ReturnProposal(summary, proposal_text)`, P14 suggestion, outbox+reaper, A6 calls surface | `ReturnProposal` v2 (commitments, follow_up_tasks, follow_up_reminders, follow_up_draft, uncertainties), prompt v2, `PhoneCall.debrief` JSONB (migration+ADR), rich chat card (InterestNotificationCard pattern, typed metadata), items = chat intents, A6 re-display | debrief survives a missed notification; synthesis-failure fallback intact; replay-checked migration |
| R01 | `/dashboard/spaces` + `POST /rag-spaces/{id}/toggle` + chat indicator (hidden at 0 active) | 5th destination in `DASHBOARD_DESTINATIONS` (both navs), desktop nav table-driven, quick-toggle dropdown on the chat spaces indicator | reachability + mobile-nav e2e green at pinned widths, else plan B |
| N-13 | 6 localized manifests, 3 shortcuts, `share_target`, InstallHint | enriched shortcuts ×6 (quick add `?draft=`, voice `?voice=1`, fix stale spaces link), `?voice=1` wiring | 6 manifests coherent (parity check), deep links tested, mic fallback verified |
| SLASH | 10 static commands + dialogue skills, WAI-ARIA combobox | `chat_shortcuts` JSONB + settings CRUD section + merge w/ reserved prefix + Alembic migration | CRUD works; collisions impossible; JSONB round-trip tested |
| N-07 | time-only model, executor runs full pipeline, chat tools ADR-140, HITL guard | migration (`trigger_kind` default `time`, `condition_config`, `condition_state`, `requires_approval`), per-type evaluators + boot completeness assert (ADR-085), dedup ledger, studio UI, ADR-140 tools synced, ADR | existing routines migrate with zero behavior change (dedicated test); each condition type tested + dedup case; "propose first" delivers a chat confirmation |
| K01 | 14 state×provider accordions, heterogeneous styles | one visual grammar (status badge + icon + count) across 14 triggers + 3 card types | visual audit of 14 states; status announced not just colored; a11y ratchet untouched |
| C-02 (new) | nothing listens to selection; no sheet primitive | selection listener scoped to assistant bubbles, popover/bottom-sheet, 7 actions as chat intents with quoted passage | multi-message selection refused; empty selection ignored; keyboard-accessible equivalent exists |
| N-09 (new) | `OpenLoop.counterparty`, `PhoneCall.callee_display`, memories, birthdays, briefing fetchers | new `relations/` domain (briefing pattern), Relations page, 360° prep = chat intent | sections degrade independently; identity mismatches visible as best-effort |

---

## Lots & gates

Order: A → B → C → D → E → F → G (dependencies: C reuses B's freshness patterns is
false — C depends only on A1; G depends on B (freshness) + C (intents)).

Invariant gates for EVERY lot: `task lint` · `task test:frontend` (+ `:coverage` on UI
lots) · `task test:backend:unit:fast` (lots with backend) · targeted e2e · i18n parity
×6 · no ratchet regression · self code-review. Before program end: `task ci:fast`;
migrations ⇒ `task db:migrate:replay-check`.

- **Lot A** (S): R01 + K01 + N-13 + SLASH admin. e2e: `dashboard-header-reachability`,
  `mobile-nav`. Backend: users migration (`chat_shortcuts`) + prefs endpoint.
- **Lot B** (M): D-04. Backend briefing + frontend cards. Schema mirrors synced.
- **Lot C** (M): QW-24. ADR (A4 amendment). Card action rows + `?intent=`.
- **Lot D** (M/L): C-02. New `ui/` sheet primitive + selection hook + action menu.
- **Lot E** (M): T01. Migration (`phone_calls.debrief`) + prompt v2 + chat card + ADR.
- **Lot F** (L): N-07. Migration + evaluators + studio UI + tools sync + ADR.
- **Lot G** (XL): N-09. New read-only domain + page + fetchers + caches.

---

## Status tracker

| Lot | Status | Evidence |
|---|---|---|
| A — R01/K01/N-13/SLASH | **DONE 2026-07-29** | `task lint` green (ratchets held); frontend 3980/3980; backend 14704 (+16 shortcuts, +data-map entry); e2e 35/35 (reachability ×6 locales, mobile-nav, deep-links, search, chat header); `db:migrate:replay-check` OK (d4e5f6a7b8c9). Plan B EXECUTED: nav boundary md→lg (5 destinations clip in fr/de/es/it at 768–1024, measured); `MOBILE_SURFACES.dashboard-nav` minWidth 768→1024. Review fixes: toggle failure toast in quick-toggle menu; md→lg docstrings. Pins consciously updated: settings tokens 30→31, manifest shortcuts 3→5, mobile-nav menuitems 4→5. N-13 spotlight = finite CSS animation applied imperatively (react-hooks + CC ratchets forced the design — better one). |
| B — D-04 | **CODE+TESTS DONE 2026-07-29** | Backend: additive `CardSection` fields, `lastgood` side cache (TTL setting `briefing_last_good_ttl_seconds`), `/refresh-cards` (per-card retry w/o LLM), `_reject_hidden_sections` shared guard; 9 new tests (`test_stale_freshness.py`), briefing suite 166 green. Frontend: badge survives errors (stale-dated, `· cache` suffix), stale body under error banner, freshness line, `timeAgoLabel`; `BriefingCard.freshness.test.tsx` 7 tests; dashboard+hooks 625 green. No purge-on-disconnect needed: disconnect ⇒ NOT_CONFIGURED path, stale only rides ERROR (recorded). Consolidated gates pending. |
| C — QW-24 | **CODE+TESTS DONE 2026-07-29** | **ADR-173** (+index): `?intent=` executes via `sendMessageFromPresent`, consume-once+strip-before-send, quota⇒draft+toast, waits on api/isTyping. `useAutoSendIntent` (6 tests, StrictMode-pinned), `chatIntentHref`, `CardItemActions` (sibling chips — no nested buttons), 5 cards wired (route chip only with location; document "ask" PREFILLS), `intents_exec.*` ×6. `complete_task` VERIFIED direct-execute (reversible) — intent inherits chat pipeline exactly. HITL-pending guard consciously dropped (composer never blocks on HITL; recorded deviation). |
| D — C-02 | **CODE+TESTS DONE 2026-07-29** | `useTextSelection` (useSyncExternalStore, debounced, scope+cross-scope refusal — 5 jsdom tests), `useMediaQuery`, `SelectionActions` (desktop toolbar / mobile sheet, NO scroll-lock — ADR-171 doctrine; quote frozen from snapshot, preventDefault on pointer-down; 7 actions, "ask" prefills; 7 tests), `data-selection-scope` per assistant bubble, `SELECTION_QUOTE_MAX_LENGTH`, `chat.selection.*` ×6. "Save to space" mapped to memory-remember (no per-quote space API; recorded). |
| E — T01 | **CODE+TESTS DONE 2026-07-29** | **ADR-174** (+index): `ReturnProposal` v2 (additive debrief fields, v1 shape still validates), prompt enriched in place (v1 = live version, repo practice), `phone_calls.debrief` JSONB (migration e5f6a7b8c9d0 — REPLAY-CHECK PENDING), reaper purges it with summary, empty⇒NULL; metadata `proactive_phone_call` carries it; `CallDebrief` dual-posture (chat informational / settings actionable via `?intent=`/`?draft=`), `settings.telephony.debrief.*` ×6; backend telephony 148 green (+4 debrief), frontend 13 green; tsc clean. |
| F — N-07 | **CODE+TESTS DONE 2026-07-29** | **ADR-175** (+index): `trigger_kind`/`condition_config`/`condition_state`/`requires_approval` (migration f6a7b8c9d0e1, existing rows → time/false, replay-checked). Evaluators in `infrastructure/scheduler/condition_evaluators.py` (NOT the domain — reads via briefing fetchers, avoids the domain↔domain cycle; boot completeness assert, ADR-085) — 5 condition types, dedup by fact fingerprint, NEVER raise. Executor: condition gate + propose-first (`?intent=` notification, ADR-173) via `repo.reschedule` (never counts as exec); loads ORM User for evaluators (get_user_by_id returns UserProfile — was a latent bug). Studio UI in `ScheduledActionsSettings` (kind/condition/query/approval); chat ADR-140 tool creates `time` routines (additive defaults → same object, documented). Tests: condition evaluators (15), schemas (24), executor regression pinned. i18n ×6. |
| G — N-09 | **CODE+TESTS DONE 2026-07-29** | **ADR-176 PENDING** (write it at finalize): new read-only `relations/` domain (briefing pattern — own-session sequential queries, no new table), aggregates open loops + calls + memories per person; identity best-effort (accent/case fold → EXACT/NORMALIZED, stated in UI). `/relations` + `/relations/{name}` (router wired). Frontend: `useRelations`, `/dashboard/relations` page (overview⇄detail), 360° prep = `?intent=` (ADR-173); reached from ForYou card heading + settings search — NOT a 6th nav dest (header clip). Birthday/contacts matching = documented phase 2 (no dead field). Tests: service (5), overview list (3), detail panel (5). i18n ×6 (plural suffixes, zh duplicated). |

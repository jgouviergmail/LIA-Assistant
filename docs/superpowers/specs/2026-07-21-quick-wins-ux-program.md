# Quick Wins UX Program — Verified Design & Multi-Session Roadmap

**Date:** 2026-07-21 · **Status:** awaiting arbitration sign-off, no lot started
**Baseline:** HEAD `fa5234db` + the **uncommitted** widgets wave in the working tree (ADR-136/137, D1-D6 — see memory `project_widget_defects_2026_07`). Lot 1 must ship inside that pending release.
**Scope:** QW-11, QW-12, QW-2, QW-9, QW-10, QW-5 (execution order).

Every claim below was verified in-code on 2026-07-21 (file:line evidence inline). Three factual
corrections vs the original briefs are marked **[CORRECTED]**.

---

## How to resume (session protocol)

Each implementing session follows this ritual — do not skip steps:

1. Read memory `project_quick_wins_ux_2026_07.md`, then this document. The **status tracker**
   (bottom) says where the program stands.
2. Check the real state: `git log --oneline -5`, `git status`. If HEAD moved past the baseline,
   re-verify the volatile assumptions of the target lot (exact line numbers, ratchet headroom in
   `apps/api/tests/unit/file_size_baseline.json`, presence of the uncommitted widgets wave).
3. Write the **granular implementation plan for that lot only** in
   `docs/superpowers/plans/YYYY-MM-DD-qw-<lot>.md` following `superpowers:writing-plans`
   (complete code in every step, TDD, bite-sized tasks) against the *current* tree.
4. Present the granular plan for approval (project rule: findings → green light → implement).
5. Implement **inline** (user rule: no subagents), TDD, one lot per session by default.
6. Run the lot's gates (per-lot list below + global gates). Evidence before any "done" claim.
7. Update the status tracker here + the memory file. **Never commit/push — the user does.**

Session boundaries: 1 lot = 1 session by default. Lots 2 (QW-12) and 4 (QW-9) are small and
touch disjoint files — they may be grouped opportunistically if a session has capacity left
*after* gates pass.

---

## Verified findings (evidence base)

### QW-2 — Full history search
- Backend `GET /conversations/me/messages` supports `search` (ILIKE, accent-sensitive,
  2–200 chars: `CONVERSATION_SEARCH_MIN_LENGTH/MAX` in `core/constants.py:1228`) and keyset
  `before` — `conversations/router.py:96-109`, `conversations/repository.py:349-365`.
  `search` + `before` combine, so server-result pagination works out of the box.
- **[CORRECTED]** The `unaccent` extension is ALREADY installed (migration
  `2026_02_04_0002-add_unaccent_extension.py`) and used by admin user search
  (`users/repository.py:248-249`); test DBs create it too (`tests/conftest.py:605-608,702-703`).
  No migration needed — only apply `func.unaccent()` to the messages query. The integration test
  `tests/integration/domains/conversations/test_messages_search.py` deliberately LOCKS the
  accent-sensitive contract and must be updated in the same change.
- LIKE wildcards are NOT escaped today (`ilike(f"%{search}%")`) — escape `%`/`_`/`\` when touching.
- Frontend: client-only filter `toLowerCase().includes` on loaded messages
  (`chat/page.tsx:294-302`); field hidden below the `mobile` breakpoint —
  **[CORRECTED]** `--breakpoint-mobile: 880px` (`styles/globals.css:13`), so tablets are hit too.
  No counter, no highlight. `?search=` never called by the frontend (`useConversation.ts` fetchPage).
- **[CORRECTED]** The FAQ highlight (`FAQContent.tsx:141-209`) injects HTML via
  `dangerouslySetInnerHTML` — forbidden for LLM content (XSS boundary, `apps/web/CLAUDE.md`).
  In-bubble highlighting must be a **post-sanitize rehype plugin** emitting fixed-class `<mark>`,
  modeled on `src/lib/rehype-math-in-text.ts` (documented sanitize-exempt stage).
  `normalizeSearchText` (`lib/utils.ts:75`) IS reusable as-is for matching.
- Keyset is strict `<`: jumping to a result requires `before = created_at + 1 ms` client-side.
  There is NO "load newer" mechanism (scroll-up only) → a jump needs a "history view" state with
  a return-to-present path. `ChatMessage` is memoized — highlight prop must be debounced.

### QW-9 — Actionable briefing cards
- Items are inert `<li>` in all cards: `MailsCard.tsx:48-59`, `AgendaCard.tsx:38-61`,
  `BirthdaysCard.tsx:39-59`, `RemindersCard.tsx:37-48`. Quick Access = Help + Settings only
  (`QuickAccessCompact.tsx:26-39`). Data available per item: mail `subject`/`sender_email|name`,
  event `title`/`start_local`, birthday `contact_name` (FULL name, not first name), reminder
  `content`/`trigger_at_local`.
- `?draft=` pattern is live end-to-end: emit `Page7Examples.tsx:163`, read
  `chat/page.tsx:44-47` ("never auto-sent"), prefill in `ChatInput` on mount.
  Improvement folded in: strip `?draft=` from the URL after reading (replaceState) — also fixes
  the latent onboarding re-prefill-on-F5 defect.

### QW-10 — Portrait discoverability
- Portrait block (full/brief, compiled_at, feedback→recompile) at `JournalsSettings.tsx:395-450`.
  `GET /journals/portrait` exists (`journals/router.py:513`), router gated by the global
  `journals_enabled` flag (`api/v1/routes.py:81-84`) → tolerate 404 in any new hook.
- **[CORRECTED]** `?section=` is NOT generic: only `section === 'connectors'` is handled
  (`settings/page.tsx:102-111`). `JournalsSettings` lives in the **Features tab, group
  "Automation & Tracking"** (superuser AND non-admin), NOT in Identity & Memory → the new entry
  is a cross-group shortcut and `?section=` must be generalized (value → tab + accordion + scroll).

### QW-11 — UX-core V2 finishers
- Trace: ADR-133 "Périmètre V2 (différé)" — persist to `message_metadata` at archive, PII guard
  (i18n keys only, never `detail` nor raw reasoning → the reloaded trace has NO 💭 block),
  round-trip test mandatory. SSE steps already carry `emoji/i18n_key/category`. All
  `execution_step` chunks flow through ONE generator in the streaming service (`updates` mode
  `streaming/service.py:473`, `custom` mode `:492`) → single accumulation point, reset on
  `router_decision` (mirrors frontend semantics incl. HITL out-of-scope V1). Archive site:
  `agents/api/service.py:1286`; patterns to imitate in the same file: `persistable_widgets`
  (ADR-137) and `patch_message_metadata` psyche pattern (`:1335`).
  Frontend hydration: extend `toUiMessage` (`useConversation.ts:145-186`) and make
  `ExecutionTraceStep` accept an optional `i18nKey` (live steps store translated `label`;
  persisted steps store the key, resolved at render).
- Connector notice: ADR-134 "Périmètre et limites" — `provider_resolver.py:73` requires
  `ConnectorStatus.ACTIVE`; a broken connector then yields `ConnectorNotEnabledError` with no
  banner. **Design constraint (verified):** `handle_tool_exception` is SYNC
  (`runtime_helpers.py:402-406`) → enrichment must happen AT RAISE TIME (async context, the
  Redis-cached connector list is already in hand in `resolve_active_connector`): add optional
  `functional_category` + `error_connector_type` to `ConnectorNotEnabledError`, set via a common
  factory helper; `classify_connector_exception` (sync) just reads the attribute. Covers the 3
  ADR-134 emission points unchanged. `ConnectorStatus.REVOKED` exists — excluded (arb. #4).

### QW-12 — Chat header hygiene
- Green pill pulses permanently: `chat/page.tsx:540-545` (`animate-pulse`); offline (rose) and
  processing (amber) states just above — those stay. Totals banner `page.tsx:610-629` — already
  gated by `tokens_display_enabled` AND already hidden < 880 px (costs a line on desktop only).
- `ContextUsagePill` is present from page load (`hydrateContextUsage` seeds it from `/me/totals`),
  has a tooltip + a < 360 px tap variant → totals fold into that tooltip
  (keep `tokens_display_enabled` gating on the cost/token lines).

### QW-5 — 👍/👎 on ordinary responses
- Pattern to imitate: `InterestFeedbackButtons` — an **internal, non-exported** component of
  `ChatMessage.tsx:72-119` (extract/generalize, don't import); persistence
  `mark_interest_feedback_submitted` (`conversations/repository.py:806-880`) = **server-side
  atomic `jsonb_set(jsonb_set(coalesce(...)))` UPDATE, user-scoped via conversation subquery** —
  the canonical JSONB form for the verdict. Hydration via `message.metadata.feedback_submitted`
  (`ChatMessage.tsx:459-464`). Endpoint shape: `interests/router.py:654-709` (ownership, commit,
  metric in `suppress`, i18n response via `APIMessages`).
- Journals: `evidence_outcome` increments system-managed counters
  (`journals/service.py:279-286`); T→T+1 uses `injected_journal_ids` — declared in
  `MessagesState` (`agents/models.py:421-424`) but NOT persisted per message → archive it into
  `assistant_metadata` (IDs only, no PII).
- Message identification (verified): the `done` chunk is emitted at `agents/api/service.py:1611`,
  AFTER archive (`:1286`) → `archived_message_id` can ride the done metadata. Trap: TWO
  `DoneMetadata` types (ADR-117 — live vs synthesized-on-resume); the synthesized one may lack
  the id → keep a `run_id` fallback (run_id may match several rows in HITL flows — prefer id).
- Metric nuance: `track_proactive_feedback` already exists (Grafana dashboard 13) —
  `response_feedback_total{verdict}` is the first satisfaction measure **for ordinary responses**.
- Edge case: verdict CHANGE (👍↔👎). Journal counters have no decrement path → counters are fed
  on the FIRST verdict only; later changes update the persisted verdict + metric, never
  re-increment.

---

## Open arbitrations (blocking lot start)

| # | Topic | Recommendation | Status |
|---|-------|----------------|--------|
| 1 | QW-2 jump-to-result behavior | "History view" state: discreet banner + "back to present" button; sending a message auto-returns to present first | **VALIDATED 2026-07-21** |
| 2 | QW-2 in-bubble highlight | Post-sanitize rehype plugin (only XSS-conformant option) — NOT the FAQ component | **VALIDATED 2026-07-21** |
| 3 | QW-5 journals coupling | V1 = persisted verdict + evidence/contradiction counters on injected entries (arithmetic only, no LLM) + metric; 👎 free-text stored in metadata and, if journals enabled, dropped as an L0 correction entry WITHOUT recompilation; counters fed on first verdict only | **VALIDATED 2026-07-21** |
| 4 | QW-11 REVOKED status | Excluded from the reconnect banner (deliberate revocation ≠ failure); ERROR only, per ADR-134 | **VALIDATED 2026-07-21** |
| 5 | QW-12 nominal state | No pill at all in nominal state (no static dot) | **VALIDATED 2026-07-21** |
| 6 | QW-10 entry when no portrait | Entry only shown when a compiled portrait exists (no teaser) | **VALIDATED 2026-07-21** |
| 7 | Release sequencing | Lot 1 (QW-11) ships inside the pending widgets release; lots 2-6 after | **VALIDATED 2026-07-21** |

All 7 recommendations validated as-is by the user on 2026-07-21 ("ok avec tout"), with a standing
mandate: autonomous execution of all lots, maximum test coverage (unit/back/front), deep code
review at every step, inline only, stop only for a new arbitration need.

---

## Cross-cutting conformity constraints (apply to every lot)

- **Size ratchets (measured 2026-07-21,** `apps/api/tests/unit/file_size_baseline.json`**):**
  `agents/api/service.py` cap 1052 · `streaming/service.py` cap 1335 ·
  `runtime_helpers.py` cap 674 (**~2 SLOC margin**) · `conversations/repository.py` cap 688.
  Consequences: trace capture → NEW module `services/streaming/trace_capture.py` (mirror
  `data_registry/message_widgets.py`); QW-11 enrichment factory → `provider_resolver.py` or a
  small connectors module, NEVER `runtime_helpers.py`; QW-5 repo method → check headroom first,
  else a cohesive new module. Wiring lines minimal everywhere. Re-measure headroom at session
  start (the uncommitted widgets wave moves these numbers).
- **JSONB:** server-side `jsonb_set` UPDATE (imitate `mark_interest_feedback_submitted`) or
  new-dict at archive; never in-place mutation (CI AST guard).
- **Settings vs constants:** persisted-trace byte cap = Settings field + `.env.example` +
  `.env.prod.example` (imitate `widget_persist_max_bytes`). Frontend "recent portrait" threshold =
  frontend constant. New metadata keys = `FIELD_EXECUTION_TRACE`, `FIELD_RESPONSE_FEEDBACK`,
  `FIELD_INJECTED_JOURNAL_IDS` in `core/field_names.py`.
- **i18n ×6** (en, fr, de, es, it, zh — strict parity hook; duplicate `_one` for zh plurals).
  Backend responses via `APIMessages`. Trace persists i18n KEYS only.
- **PII:** the 👎 comment is content → never at INFO. Counters/IDs at INFO.
- **SSE:** additive metadata only; update BOTH `DoneMetadata` types together (ADR-117 trap).
- **Error taxonomy:** typed exceptions + attribute reads; never string matching.
- **XSS:** any new HTML-adjacent rendering goes through the sanitize pipeline; highlight plugin
  runs post-sanitize and emits fixed-class `<mark>` only.
- **Async:** no shared `AsyncSession` across tasks; sequential loop fine for a handful of updates.
- **Tests:** round-trip test for the trace archive shape; reducer test per new action; settings
  thresholds read from `settings`, never hardcoded; a11y role/name oracles for new controls.
- **Global gates:** `task lint` + `task test:backend:unit:fast` (backend lots) ·
  `task test:frontend` + `pnpm exec tsc --noEmit --incremental false` + `pnpm a11y:ratchet &&
  pnpm react-hooks:ratchet && pnpm cc:ratchet` (frontend lots) · i18n parity · runtime proof in
  the Docker dev containers (never local builds; `docker restart lia-web-dev` before browser
  validation — the container does NOT hot-reload host edits).

---

## Lot specifications

### Lot 1 — QW-11: close the UX-core works (ships with the widgets release)
**Backend trace:** new `services/streaming/trace_capture.py` — accumulator fed at the single
streaming chokepoint: keep `{emoji, i18n_key, category}` per `execution_step`, skip
`step_type in (reasoning, tool_error)`, drop `detail`, reset on `router_decision`, cap keeping
the TAIL (settings-driven byte/step cap). Merge `{steps, duration_ms}` into
`assistant_metadata[FIELD_EXECUTION_TRACE]` at the archive site next to `with_persisted_widgets`.
Round-trip test. **Frontend:** `toUiMessage` maps metadata → `executionTrace`;
`ExecutionTraceStep.i18nKey?` resolved at render (`ExecutionTraceDisclosure`); reloaded trace has
no reasoning block (assumed, ADR-133 guard).
**Backend notice:** `ConnectorNotEnabledError` gains optional `functional_category` +
`error_connector_type`; factory helper in `provider_resolver.py` consults the already-fetched
cached connector list for an ERROR-status connector of the category; set at the ~8 raise sites
via the factory; `classify_connector_exception` maps the attribute → `reconnect` notice (reuses
`connector_error_notices_total`, contract unchanged).
**Tests:** accumulator (reset/cap/skip rules), archive round-trip, hydration, classification,
notice-at-resolution integration. **Docs:** ADR-133/134 V2 delivered notes.
**Effort:** S+S.

### Lot 2 — QW-12: chat header hygiene
Remove the nominal green pill (arb. #5); keep offline/processing. Fold totals
(TOTAL/IN/OUT/CACHE/GOOGLE/cost) into the `ContextUsagePill` tooltip, `tokens_display_enabled`
gating preserved; delete the banner block. Frees header space used by Lot 3's mobile search.
**Tests:** header states, tooltip content w/ and w/o `tokens_display_enabled`. **Effort:** S.

### Lot 3 — QW-2: complete history search
(1) Client filter via `normalizeSearchText` + debounce; (2) `lib/rehype-search-highlight.ts`
post-sanitize plugin + status line "N results in loaded messages" (i18n plurals ×6);
(3) "Search entire history" when `hasMoreOlder` → dated server-result list (`search`+`before`
pagination), click → jump (`before = created_at + 1 ms`) + history-view state per arb. #1,
disabled while streaming; (4) backend `func.unaccent()` on both sides of the ILIKE + wildcard
escaping + update the contract-locking integration test; (5) mobile 🔍 icon expanding an overlay
bar (< 880 px). **Tests:** filter/highlight (incl. accents, regex-special chars, markdown
boundaries), jump + return-to-present, min-2-chars gating, backend accent tests (é↔e both ways),
escaping. **Effort:** M.

### Lot 4 — QW-9: actionable briefing cards
Items become real `<button>`s (translated accessible names); per-domain intent strings i18n ×6
interpolating item fields; `router.push(…/chat?draft=<intent>)`; reminders → plain chat open;
strip `?draft=` after read (also fixes onboarding). Verify `BriefingCard` has no interactive
wrapper (nesting). **Tests:** role/name, keyboard activation, draft URL encoding, long subjects.
**Effort:** S.

### Lot 5 — QW-10: portrait discoverability
Generalize `?section=` (value → tab/accordion/scroll, keep URL-cleaning); "What LIA understands
about you" shortcut entry in Identity & Memory (visible only with a compiled portrait, arb. #6);
dashboard hint under hero when `compiled_at` recent (frontend constant threshold, localStorage
dismissal keyed by `compiled_at`, tolerate 404 when flag off); portrait mention on onboarding
`Page4Memory`. **Tests:** section deep-link (both superuser tab layouts), hint
visibility/dismissal, 404 tolerance. **Effort:** S.

### Lot 6 — QW-5: response feedback
`archived_message_id` added to BOTH `DoneMetadata` types; archive `injected_journal_ids` (IDs
only) into assistant metadata (state → archive or `patch_message_metadata`);
`POST /conversations/me/messages/{message_id}/feedback` (ownership user-scoped → 404, verdict +
optional comment, idempotent, verdict-change rule per finding above); persistence via the
`jsonb_set` pattern; journal counters via sequential `update_entry(evidence_outcome=…)` (first
verdict only, journals-enabled guard); `response_feedback_total{verdict}` in `metrics_registry`;
UI: extract/generalize the feedback-buttons pattern — visible on hover next to Copy, EXCLUDED for
proactive (`isProactiveInterest`/`proactive_*`), system, streaming messages; 👎 unfolds one-line
optional comment; hydration cross-device from metadata; never auto-regenerate. New ADR-138.
**Tests:** endpoint (ownership, idempotence, verdict change, journals off), repo jsonb, UI
show/hide/hydrate, done-metadata propagation, metric. **Effort:** M.

---

## Status tracker (update at end of every session)

| Lot | Content | Status | Session date | Granular plan | Evidence |
|-----|---------|--------|--------------|---------------|----------|
| 1 | QW-11 trace + notice | **DONE** | 2026-07-22 | plans/2026-07-21-qw-lot1-trace-notice.md | backend 10 641 unit fast green (ratchet incl.), frontend 2 228 green + tsc/eslint/a11y/hooks/CC ratchets, `task lint` green; RUNTIME dev: phase A = weather turn → archived row carries `execution_trace` (6 i18n steps + duration_ms); phase B = ERROR-status gmail row → SSE `tool_error {google_gmail, reconnect}` observed (script `scratchpad/qw11_runtime_proof.py`, QA user qa.qw11@example.com kept active for later lots) |
| 2 | QW-12 header | **DONE** | 2026-07-22 | inline (small lot) | nominal state silent (offline/processing kept), totals banner folded into `ContextUsagePill` tooltip (`totals` prop, gating page-side, same token-badge idiom as bubbles), `chat.input.status.online` removed ×6 (parity script green); frontend 2 231 green, tsc/eslint/prettier clean, 3 ratchets hold |
| 3 | QW-2 search | **DONE** | 2026-07-22 | inline (spec section) | backend: `unaccent(ILIKE)` both sides + wildcard escaping, contract test rewritten (5 integration green on real DB); frontend: accent-insensitive client filter + counter, `rehype-search-highlight` post-sanitize plugin (`lia-search-mark`, skips code/KaTeX; 9+4 tests), `findNormalizedMatches` shared util, server results panel w/ keyset pagination + jump (`before=+1ms`) + history-view banner + auto-return-on-send (hook 10 tests, panel 7 tests — CC-decomposed), mobile 🔍 row < 880px, 15 i18n keys ×6 (parity green); suites: backend 10 644 green, frontend 2 266 green, tsc/eslint/lint global clean, 3 ratchets hold |
| 4 | QW-9 briefing | **DONE** | 2026-07-22 | inline (spec section) | 4 cards' items are real labelled `<button>`s (accessible name = the intent itself) → `router.push(chatDraftHref(lng, intent))`; reminders open the chat plainly; consumed `?draft=` stripped via history.replaceState (fixes the onboarding F5 re-prefill too); `dashboard.briefing.intents.*` ×6 (parity green); 4 interaction tests (role/name oracles); frontend 2 270 green, tsc/eslint/prettier clean, 3 ratchets hold |
| 5 | QW-10 portrait | **DONE** | 2026-07-22 | inline (spec section) | `?section=` generalized (journals → Features tab + accordion + scroll via `settings-section-<value>` ids on SettingsSection); `PortraitShortcut` at the head of Identity & Memory ×2 layouts (shown only with a compiled portrait, arb #6; light `useJournalPortrait` hook, gateable); `PortraitHint` under the dashboard hero (7-day recency constant, localStorage keyed by compiled_at, gated on `features.journals_enabled` — AppConfig type aligned with the backend payload); portrait tip on onboarding Page4; keys ×6 (parity green); 8+2 tests; frontend 2 278 green, ratchets hold |
| 6 | QW-5 feedback | **DONE** | 2026-07-22 | inline (spec section) | ADR-138 written + indexed. `POST /conversations/me/messages/{id}/feedback` (owner-scoped jsonb_set, 404 hides existence, module `response_feedback.py` — repository was 9 SLOC from its cap); done chunk carries `archived_message_id` (archive precedes done — verified); history rows carry `message_db_id` via toUiMessage; journals coupling through an INJECTED PORT (`JournalFeedbackHooks` + `journals/feedback_hooks.py` + startup registration) after the F009 guard caught the conversations↔journals cycle a lazy import created; counters on FIRST verdict only; 👎 comment → L0 user_correction, no consolidation; `response_feedback_total{verdict}`; UI chips next to Copy (aria-pressed, hover idiom, hydration, Escape/Enter); CC baseline LOWERED 74→60 (pure-helper extraction); keys ×6 parity green; 6 integration (real DB) + 4 component tests; backend 10 644 green, frontend 2 282 green, lint + cycles 31/31 baseline; RUNTIME phase C: real turn → done id → POST feedback → metadata reread `{thumbs_down, comment}` → foreign id 404 |

**Decisions log** (fill as arbitrations land):
- 2026-07-22 · Lot 1: persisted trace DEDUPES by i18n_key per turn (exact mirror of the frontend
  `emittedStepKeysRef` early-return — a FOR_EACH shows ONE tool step live, so does the persisted
  trace). Discovered during the deep-review parity pass; locked by 4 dedicated tests.
- 2026-07-22 · Lot 1: `ConnectorTool.execute` does NOT raise on unresolved category (returns a
  formatted error) → notice emitted DIRECTLY at that site via `emit_connector_notice` (new
  public function; the exception path stays classifier-based). Discovered in the raise-site audit.
- 2026-07-22 · Lot 1: ratchet pressure on `streaming/service.py` absorbed by consolidating the
  4 duplicated per-chunk metric blocks into `_track_and_observe` and the if/elif event-type chain
  into a dict — net shrink, caps untouched.
- 2026-07-22 · Runtime proofs run as the dedicated QA user `qa.qw11@example.com` (registered via
  the API, activated by SQL, no connectors) with `scratchpad/qw11_runtime_proof.py`-style httpx
  scripts — same pattern as `scripts/perf/measure_ttft.py`. Trap confirmed: `connectors` rows
  store enum NAMES uppercase (`GOOGLE_GMAIL`, `ERROR`) — a lowercase row poisons
  `get_user_connectors` for the whole user.
- 2026-07-22 · **Browser validation DONE** (real Chrome on the dev stack, QA user via the real
  login): nominal header WITHOUT the status pill + context pill present (QW-12); ⚙ "Afficher les
  détails d'exécution" rendered ON A RELOADED HISTORY ROW and expanded to translated steps
  ("étapes · 6.1 s — 🧭 Analyse… 💬 Génération…") (QW-11 hydration); search counter row
  ("1 résultat dans les messages chargés") + accent-insensitive in-bubble `<mark>`
  ("probabilites" highlights "probabilités") (QW-2); 👍/👎 chips hydrated `aria-pressed` from the
  phase-C verdict, verdict CHANGE clicked in-browser → DB reread `{"verdict": "thumbs_up"}` +
  `response_feedback_total{verdict="thumbs_up"} 1.0` on /metrics (QW-5); dashboard hero +
  QuickAccess render, portrait hint correctly ABSENT for a user without portrait (QW-10 arb #6).
  QW-9 card clicks not exercisable (QA user has no connectors → cards hidden) — covered by the
  4 role/name interaction tests.
- 2026-07-22 · **Environment repair (pre-existing drift, unrelated to the program):** the
  machine's LAN IP moved 192.168.0.29 → **192.168.0.30** while `.env` still pointed at `.29`
  (NEXT_PUBLIC_API_URL/CORS_ORIGINS/FRONTEND_URL/API_URL…) — browser→API calls timed out for
  ANY browser session. Fixed by `sed .29→.30` in `.env` + **`docker compose up -d
  --force-recreate api web`** (a plain `docker restart` does NOT re-read the env — trap).
  Login must go through the SAME-SITE origin `https://192.168.0.30.nip.io:3000` (a
  `localhost:3000` page cannot receive the API's cookie cross-site).

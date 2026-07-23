# UX Refinements Program — Verified Design & Multi-Session Roadmap

**Date:** 2026-07-22 · **Status:** arbitrations signed off, no lot started
**Baseline:** HEAD `aefdf1bd` (v1.25.14). **Working tree is NOT clean**: a parallel
landing/FAQ/demo work stream sits uncommitted (13 modified + 9 untracked files —
`landing/`, `faq/`, `demo/`, `sitemap.ts`, `api-client.ts`, 2 e2e specs). Verified
2026-07-22: **zero file overlap** with this program's lots (only `api-client.ts` is
shared territory and no lot plans to touch it). Never revert, commit, or reformat those
files; re-run `git status` at every lot start and re-check overlap.
**Scope:** 10 lots — PERSO, A7, A3, A2, B4, A10, B5, A4, A6 (sub-lots 9a/9b), B12
(execution order below).

Every claim below was verified in-code on 2026-07-22 (file:line evidence inline).
Four factual corrections vs the original briefs are marked **[CORRECTED]**.
Sibling program docs (same format): `2026-07-21-quick-wins-ux-program.md`,
`2026-07-21-interdomain-intelligence-program.md`.

---

## How to resume (session protocol)

Each implementing session follows this ritual — do not skip steps:

1. Read memory `project_ux_refinements_program.md`, then this document. The **status
   tracker** (bottom) says where the program stands.
2. Check the real state: `git log --oneline -5`, `git status`. If HEAD moved past the
   baseline, re-verify the volatile assumptions of the target lot (exact line numbers,
   ratchet headroom, presence/absorption of the uncommitted landing/FAQ stream).
3. Write the **granular implementation plan for that lot only** in
   `docs/superpowers/plans/YYYY-MM-DD-uxr-<lot>.md` following `superpowers:writing-plans`
   (complete code in every step, TDD, bite-sized tasks) against the *current* tree.
4. Present the granular plan for approval (project rule: findings → green light →
   implement).
5. Implement **inline** (user rule: no subagents), TDD, one lot per session by default.
6. Run the lot's gates (per-lot list below + global gates). Evidence before any "done"
   claim. Runtime proof happens in the Docker dev containers — remember
   `docker restart lia-web-dev` before any browser validation (host edits do NOT hot
   reload) and `curl -sk` against the HTTPS API on :8000.
7. Update the status tracker here + the memory file. **Never commit/push — the user does.**

Session boundaries: 1 lot = 1 session by default. Lot 1 (PERSO) is small — it may be
grouped with Lot 2 (A7) if gates pass with capacity left. Lots 9a/9b (A6) are separate
sessions.

---

## Decided arbitrations (2026-07-22, user sign-off)

| # | Decision |
|---|----------|
| 1 | **A2 = (a)** Extend `InitiativeDecision` with `followup_suggestions` (2–3 chips; +50–80 output tokens per actionable turn accepted). |
| 2 | **A4 = (a)** Hand-built WAI-ARIA combobox — no `cmdk` dependency. |
| 3 | **A4 /resume = (a)** Selecting a conversational command **prefills** the input; the user presses Enter. Nothing is ever auto-sent. |
| 4 | **B5 = (a)** Open-loops view lives in a **settings section**, linked from the ForYouCard loops heading. |
| 5 | **B5 source = (a)** **No source column** in v1 (single-conversation model makes `source_ref` navigation useless — see evidence). |
| 6 | **B12 = (a)** New declarative `channels:` extension field in SKILL.md frontmatter. |
| 7 | **B4+A10 = (a)** One nullable JSONB column per feature on `users` (`briefing_preferences`, `onboarding_checklist`) — new-dict rule on every write. |
| 8 | **A6 = (b)** Ship sub-lots 9a (installability) + 9b (share text/URL + install hint). **File share_target is deferred** (needs a server-side receiving route with proxy-upload; out of program). |

Recorded micro-decisions (do not re-litigate in lot sessions; flag only if evidence
invalidates them):

- **PERSO compromise (user-acknowledged):** Copy moves to the bottom action row — on a
  very long message the user must reach the bubble's bottom to copy.
- **A2:** a chip click **replaces** the input content (explicit user action), focuses the
  input, and never sends. Chips hidden while the input is disabled (usage-blocked).
- **A2:** suggestions are plain text — rendered as React children (no markdown), server-side
  deduped, ≤3 items, ≤200 chars each, newlines stripped.
- **A3:** the follow decision **measures scroll position live at decision time** (never a
  cached flag) — kills the stale-cache class when content grows without scroll events.
- **A4:** zero-match state auto-closes the menu (Enter then sends normally); menu-open
  state suppresses the A7 ↑ recall; all key handling ignores `isComposing` (IME).
- **A10:** users already at 100% on first mount get `celebrated_at` persisted silently and
  never see the card (no retroactive noise). Any persisted `dismissed_at`/`celebrated_at`
  ⇒ the card never renders again.
- **B4:** hidden sections are **not fetched and not cache-read**; they return an explicit
  placeholder status the frontend never renders; refreshing a hidden section → 400 with a
  stable error code.
- **B5:** the API accepts `action ∈ {done, dismissed}` mapped to `closed_reason`
  `api`/`dismissed`; `conversational`/`expired` are never accepted from the API.
- **A6:** maskable icons ship as **separate files** (`purpose: "maskable"`), never a
  combined `"any maskable"` purpose (cropping bug).
- **B12:** URL import is settings-gated (`SKILLS_URL_IMPORT_*` in `.env`, parameterizable
  rule) and rides the existing hardened pipeline with zero bypass.

---

## Verified evidence base (condensed — do not re-derive)

### Lot 1 — PERSO (feedback/copy row)
- Copy button: `absolute top-2 right-2`, always visible < 880px
  (`ChatMessage.tsx:699-716`); thumbs: `absolute top-2 right-10`
  (`ResponseFeedbackButtons.tsx:103`). `mobile:` = **min-width 880px**
  (`styles/globals.css:13` — Tailwind v4 `--breakpoint-mobile`), so on phones all three
  controls overlay the first text lines. Diagnosis mechanically confirmed.
- Target pattern: `InterestFeedbackButtons` renders **in-flow** after the markdown content
  (`ChatMessage.tsx:737-742`), row `flex items-center gap-1 mt-2`.
- Feedback gate helper `responseFeedbackProps` (`ChatMessage.tsx:211-225`): null for
  proactive rows, active streams, rows without `metadata.message_db_id` — Copy-only rows
  must stay possible.

### Lot 2 — A7 (persistent draft + ↑ recall)
- No persistence anywhere: `ChatInput` is a local `useState` seeded by `initialMessage`
  (initializer-only, `ChatInput.tsx:55-80`), cleared on send (l.210). Exhaustive grep:
  no draft localStorage in pages/stores/hooks.
- **[CORRECTED]** There is **no frontend length cap** (no `maxLength` on the textarea);
  the only cap is backend `message: max_length=10000`
  (`agents/api/schemas.py:110-114`). The lot adds the mirror constant + `maxLength`.
- localStorage precedents (allowed, non-auth data): theme (`theme-context.tsx`),
  voiceModeStore (zustand persist), `useConnectorHealth` dedup key (purged at
  `useConnectorHealth.ts:234` — the purge-on-cleanup idiom to imitate on logout).
- `?draft=` is consumed then stripped from the URL (`chat/page.tsx:62-70`).

### Lot 3 — A3 (scroll-to-bottom + follow invariant)
- **[CORRECTED]** The "never hijack the reader" invariant **does not exist today**: the
  auto-scroll effect (`ChatMessageList.tsx:270-323`) runs `scrollIntoView(bottom)` on
  **every** messages update (else-branch l.313) — every streamed token yanks a reader who
  scrolled up. `wasPrependRef` only suppresses it for pagination prepends (l.279-286).
  A3 must **build** the invariant, not "respect" it.
- Load-time machinery that must survive untouched: initial pin loop
  (`INITIAL_PIN_WINDOW_MS`, l.204-261, `justPositionedRef`), scroll-preservation
  layout effect (l.333-354), gesture-armed IntersectionObserver pagination (l.360-402),
  `getScrollParent` (l.80-93 — the real scroller is an ancestor), `pinToBottom`
  smooth-scroll neutralization idiom (l.215-222).
- QW-2 integration: `historyView` + `returnToPresent()` + `ensurePresent()` + in-flight
  guard `navInFlightRef` (`useChatHistorySearch.ts:66-102`).

### Lot 4 — A2 (follow-up chips)
- **[CORRECTED]** The Initiative node emits **one** `suggestion: str | None`
  (`initiative_node.py:155-159` → state key `STATE_KEY_INITIATIVE_SUGGESTION`,
  `constants.py:2621`), optionally filled by the recurrence wrapper
  (`initiative_recurrence.py:99-109`, ADR-140), woven into prose via
  `initiative_suggestion_directive.txt` (`response_node.py:2136-2140`). 2–3 chips ⇒
  structured-output schema extension (arbitration 1).
- Coverage proven from graph edges: initiative is reached from the orchestrator, all
  domain agents (`graph.py:766-779`), draft-critique & FOR_EACH terminal decisions,
  and `react_finalize` (`graph.py:838-840`). The **conversation route bypasses it**
  → chips absent on pure-conversation turns (structural, documented). Skips: HITL just
  resolved, active skill, max iterations, no adjacent tools
  (`initiative_node.py:589-650`).
- Transport rail proven by QW-5: `done_metadata` built in `agents/api/service.py:1558-1567`
  (skipped on HITL interrupt, `archived_message_id` attached l.1563-1567) → reducer maps
  onto `message.metadata` (`chat-reducer.ts:77`) → history rows get
  `message_metadata` spread + `message_db_id` (`useConversation.ts:197-200`). A new
  `followup_suggestions` field rides the same rail, live and archived.
- **Two** DoneMetadata types to update (ADR-117 rule): `types/chat.ts:119` and the
  `STREAM_DONE` payload in `types/chat-state.ts:202-227`; symmetry pinned by
  `lib/sse-handlers/__tests__/sse-symmetry.test.ts`.
- Router resets initiative keys at turn start (`router_node_v3.py:320`). State keys must
  be declared in `MessagesState` (silent-drop trap). `list[str]` is msgpack-safe (no
  round-trip pair needed).
- Program rule (interdomain post-mortem): every new per-request mechanism declares a
  debug-panel surface (cache → emission → section).

### Lot 5 — B4 (briefing grid preferences)
- 9 sections, single source `SECTION_NAMES` (`briefing/constants.py:62-82`), already
  pinned by tests (`test_tasks_documents.py`, `test_for_you.py`).
- `CardsDisplaySettings` concerns **only** the chat display mode
  (`CardsDisplaySettings.tsx:33` → `/auth/me/display-mode-preference`) — hypothesis
  confirmed; no briefing visibility setting exists.
- `build_cards` gathers all 9 fetchers unconditionally (`service.py:166-186`), each with
  its own session (AsyncSession concurrency rule) and per-section Redis TTL
  (`constants.py:19-27`; reminders TTL=0 is special-cased with `asyncio.sleep(0)` in
  `_read_cards_from_cache`, `service.py:468-476`).
- **Three hidden CardsBundle consumers** (interdomain Lot 4 trap): `_iter_cards`,
  `_read_cards_from_cache`, `_has_content` — all must understand the hidden placeholder.
- Synthesis threshold `BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA = 2` (`constants.py:98`)
  naturally skips a mostly-hidden grid.
- `users` has **no generic preferences store** (typed columns + one MCP JSONB list,
  `users/models.py:495-500`) → new nullable JSONB column (arbitration 7).
- Heartbeat reads open loops via its own `context_sources.py` repo access, **not** via the
  briefing fetcher → hiding `for_you` cannot starve the heartbeat.

### Lot 6 — A10 (starter checklist)
- Dashboard = `TodayBriefing` (`TodayBriefing.tsx:53-64`); insertion point between
  `PortraitHint` and `QuickAccessCompact`.
- Imitable pattern: `PortraitHint` — exported pure visibility rule, localStorage
  dismissal, feature-flag gating via `useAppConfig` (`PortraitHint.tsx:40-63`).
- **[CORRECTED/PRECISION]** `/config` exposes only 5 feature flags
  (`useAppConfig.ts:27-33`: tool_approval, attachments, rag_spaces ×2, journals).
  Gating Telegram/heartbeat/skills items needs **additive** flags
  (`channels_enabled`, `heartbeat_enabled`, `skills_enabled` — settings exist backend-side)
  or 404-tolerant hooks. Decision: additive `/config` flags (cleaner, reused by B5).
- Detection hooks all exist: `useConnectorHealth`, `usePersonality`, `useVoiceMode`,
  `useChannelBindings`, `useHeartbeatSettings`, `useSpaces`, `useScheduledActions`,
  `useSkills`.
- Server persistence: new `users.onboarding_checklist` JSONB (arbitration 7), exposed via
  the existing `/auth/me` serialization (zero extra request), PATCH endpoint on the
  `display-mode-preference` idiom.

### Lot 7 — B5 (open loops view)
- v1 surface: `GET /open-loops` (+status filter, cap 100) and `POST /{id}/close`
  hard-coded `reason="api"` (`open_loops/router.py:27-72`). Router mounted only when
  `open_loops_enabled` (`api/v1/routes.py:53-56`, default OFF) → 404 when off.
- `close_loop` is an atomic conditional UPDATE claim with ownership in the WHERE
  (`repository.py:77-109`). `closed_reason` is a free `String(40)` — **no CHECK
  constraint** (migration `a4f7c2e91b3d:82-85`) → adding `dismissed` is purely additive.
- **[CORRECTED]** `source_ref` = conversation thread id
  (`open_loop_extractor.py:251`), and the product is **single-conversation per user**
  (`GET /conversations/me` singular, `conversations/router.py:51-53`) → origin-jump is
  useless; v1 drops the source column (arbitration 5).
- **No Prometheus metrics exist** for open loops (grep-verified) → create
  `open_loop_closures_total{action}` in `metrics_registry` (imitate
  `track_response_feedback`, `conversations/router.py:283-285`).
- Frontend consumption today: only the ForYouCard top-N
  (`cards/ForYouCard.tsx`) with direction-aware `?draft=` intents via
  `chatDraftHref` (`briefing-utils.ts:63-71`) — the Relancer action reuses these keys.

### Lot 8 — A4 (slash commands)
- `/resume` is real and invisible: consumed backend-side by the compaction node
  (`compaction_node.py:54,113-330`) — sending the literal text works today.
- `dialogue` flag (ADR-118) exists in the skills cache (`loader.py:48-52`) but is **not
  exposed** by `GET /skills` (`skills/router.py:56-98` — `_merge_with_cache` /
  `_skill_to_response` omit it) → 2-line additive exposure + `Skill` type.
- **No combobox/command component exists** in `components/ui/` (glob-verified) →
  hand-built WAI-ARIA combobox (arbitration 2).
- `/agenda` is **conversational** (no agenda page exists) — prefills a localized intent.
- `/recherche` opens the QW-2 search surface (`ChatSearchBar`, mobile input row included).

### Lot 9 — A6 (PWA, sub-lots 9a/9b)
- `public/manifest.json`: single SVG icon, `lang: "fr"`, `start_url: "/"`, no shortcuts /
  share_target / screenshots — hypothesis confirmed verbatim.
- Aggravating: `metadata.icons.apple` points to the **SVG** (`app/[lng]/layout.tsx:41-45`)
  — iOS does not support SVG touch icons → iOS install is degraded **today**. No app PNG
  icons exist in `public/` (glob-verified). No service worker (grep: only
  `lib/firebase.ts` references) — modern Chrome installability no longer requires one;
  offline fallback stays out of scope.
- `metadata` is a static export in the `[lng]` layout → per-locale manifest/lang requires
  converting to `generateMetadata({params})` **preserving every existing field** (SEO
  regression risk — snapshot-test it).
- Unauthenticated share lands on an auth-gated chat: the login redirect **must preserve
  the full destination URL including query** — verify `AuthProvider` returnTo behavior in
  the lot session; if lossy, add returnTo handling (hard requirement for 9b).

### Lot 10 — B12 (skills gallery + URL install)
- Hardened single pipeline confirmed: `import_service.py` S1 traversal / S2 cross-scope
  409 / S3 zip-bomb / S4 validation parity, temp staging + atomic swap (l.1-28,65-98).
  Import endpoints accept **UploadFile only** (`router.py:379-428`) — URL source missing,
  as stated.
- Current UI: flat admin/user lists with toggle/delete/download
  (`SkillsSettings.tsx:31-58`) — no gallery, no detail sheet, no category filter (the
  `category` field is already served).
- **[CORRECTED]** text/frame/image channels are **runtime script outputs** validated per
  invocation (`script_output.py:4-19,206-211`) — nothing declares them statically →
  new `channels:` extension field (arbitration 6) with default `None` (= display "text"),
  validated subset of `{text, frame, image}`, mirrored in the generator's
  `validate_skill.py` (three-way parity rule already exists for the name contract).
- Skill assets are not publicly served → preview image needs a dedicated
  `GET /skills/{name}/preview` streaming **only** `assets/preview.png` (fixed relative
  path; name validation reused as the traversal guard).

---

## Cross-cutting conformity contract (applies to every lot)

- **Gates (minimum):** `task lint`; backend touched → `task test:backend:unit:fast`;
  frontend touched → `task test:frontend` + `pnpm exec tsc --noEmit --incremental false`
  + `pnpm test:coverage` + `pnpm a11y:ratchet && pnpm react-hooks:ratchet &&
  pnpm cc:ratchet`; migrations → `task db:migrate:replay-check`; changed user journeys →
  the affected hermetic Playwright scenarios.
- **Ratchets are shrink-only** — backend SLOC caps (`file_size_baseline.json`): the big
  frozen files (`agents/api/service.py`, `ChatMessage.tsx`-scale hotspots) receive
  **minimal call-site lines only**; new logic goes to **new modules** (Lot 4:
  `followup_handoff.py`; Lot 3: extracted scroll hook). Physical-line accounting: keep
  imports compact (≤100 chars).
- **i18n ×6** with strict key parity (pre-commit hook); zh duplicates `_one`; backend
  strings through `core.i18n_*`; **prompt text only in versioned files** under
  `prompts/v1/` (Lot 4 edits `initiative_prompt.txt`, never inline).
- **JSONB writes = new dict** (AST guard); concurrent counters = server-side atomic
  (Lot 7 metrics are Prometheus, not DB); `FOR UPDATE SKIP LOCKED` untouched territory.
- **MessagesState**: every new state key declared (silent-drop trap); serialization pairs
  need round-trip tests (Lot 4 uses primitives only — exempt by design, state the fact in
  the lot plan).
- **ADR-117**: any done-chunk field lands in **both** DoneMetadata types + the
  sse-symmetry test.
- **A11y is correctness**: native buttons, stable translated names, keyboard equivalence,
  visible focus, aria-live used sparingly and politely.
- **No PII at INFO** (Lot 7: loop subjects at DEBUG only); tz-aware UTC datetimes;
  structlog only.
- **Security invariants**: no tokens in localStorage (drafts are user content — allowed,
  purged on logout); XSS boundary (chips/suggestions rendered as React children, never
  markdown/HTML); CSP per-document is test-pinned (Lot 9 touches no CSP header; Lot 10
  preview image rides the same-origin API image idiom used by attachments); widget
  sandbox invariants untouched (Lot 10).
- **Dev-container traps**: `docker restart lia-web-dev` before browser proof; `curl -sk`
  on :8000; `pnpm add` inside container ⇒ re-sync host lockfile (no new deps planned —
  arbitration 2 avoids `cmdk`).
- **Never** `git commit`/`push` — the user owns git.

---

## Lot specs

### Lot 1 — PERSO: bubble action row (Copy · 👍 · 👎)

**Goal:** move the three per-message controls from the top-right overlay into one in-flow
action row at the bottom of the assistant bubble (interest-notification pattern), fixing
mobile readability.

**Files:** `components/chat/ChatMessage.tsx` (drop the absolute Copy block, render the row
after `ExecutionTraceDisclosure`), `components/chat/ResponseFeedbackButtons.tsx` (drop the
absolute wrapper; become in-flow chips), tests
`__tests__/ChatMessage.test.tsx` + `__tests__/ResponseFeedbackButtons.test.tsx`.

**Design:** one row `flex items-center gap-1 mt-2 pt-2 border-t border-border/30`,
order Copy → 👍 → 👎; same reveal semantics as today (always visible < 880px,
hover/focus-within reveal ≥ 880px — move the opacity classes onto the row container);
the 👎 comment input stays below the row (already in-flow).

**Edge-case register:**
- Active stream: Copy stays rendered mid-stream (current behavior); thumbs stay gated by
  `responseFeedbackProps` (null while `isActiveStream`). Row renders Copy-only then.
- Proactive interest rows: keep `InterestFeedbackButtons`, never the thumbs (existing
  gate); no double row.
- Rows without `message_db_id` (cancelled runs, pre-QW-5 history): Copy-only row.
- Bubbles with skill badge / generated images / browser screenshot / trace: row remains
  the last element; no layout regression (assert order in tests).
- Keyboard reveal ≥ 880px: `focus-within` keeps controls visible while tabbing.
- User/system bubbles: untouched.

**Regression guards:** behavioral tests updated, not weakened; a11y ratchet must not move;
runtime proof = mobile-viewport browser check (<880px) + desktop hover.

**Risks:** none backend; accepted UX compromise recorded above.

---

### Lot 2 — A7: persistent input draft + ↑ recall

**Goal:** typed text survives refresh/navigation (per-user, debounced localStorage);
ArrowUp in an empty input recalls the last sent message.

**Files:** create `hooks/useInputDraft.ts`; modify `lib/constants.ts`
(`CHAT_INPUT_MAX_LENGTH = 10000` — mirror of `schemas.py:112`, cross-referenced comment;
`CHAT_DRAFT_STORAGE_KEY_PREFIX`), `components/chat/ChatInput.tsx` (add `maxLength`,
ArrowUp handler, draft wiring props), `app/[lng]/dashboard/chat/page.tsx` (priority
`?draft=` > persisted; pass last user message), the `useAuth` logout path (purge current
user's draft key); tests for hook + input + page priority.

**Design:** key `lia:chat-draft:{userId}`; ~500 ms debounce; clamp at
`CHAT_INPUT_MAX_LENGTH`; empty value ⇒ `removeItem`; restore once on mount;
clear on send and on logout. Hook signature carries `enabled = true` (future C2 aparté
exclusion documented at the signature).

**Edge-case register:**
- SSR/`window` guards + private-mode try/catch (PortraitHint idiom).
- Multi-tab: last-write-wins; single read at mount; no `storage` event sync in v1
  (documented).
- Account switch on one browser: per-user key + purge on logout (only the current user's
  key).
- `?draft=` present **and** stored draft: URL wins; once mounted, the URL draft becomes
  the stored draft via the normal debounced save (accepted).
- Voice transcription appends → draft saved (normal path). Attachments are **not**
  persisted (text-only limitation, documented).
- Browser `maxLength` silently truncates oversize pastes — matches backend cap; no toast.
- ↑ recall: only when `value === ''` && `!e.isComposing` && slash-menu-not-open (guard
  exposed for Lot 8); recalls the last **user** message; repeated ↑ keeps it (no cycling,
  v1); no-op when history has no user message; recalled text becomes the draft (normal).
- Send-failure path: input clears on send today (pre-existing contract) — draft clears
  with it; parity preserved, no new behavior.

**Regression guards:** ChatInput key-handling tests cover Enter/Shift+Enter/↑ matrix incl.
IME; `onMessageChange` propagation (geolocation prompt) asserted unchanged.

---

### Lot 3 — A3: scroll-to-bottom + reading invariant

**Goal:** floating scroll-to-bottom button with a "new response" badge, and the new
invariant: streaming never hijacks a reader who scrolled away.

**Files:** modify `components/chat/ChatMessageList.tsx` (follow decisions measure live
position; keep pin/prepend/observer machinery byte-identical); create
`components/chat/ScrollToBottomButton.tsx` + a small extracted pure helper module for
distance/threshold logic (CC discipline); modify `app/[lng]/dashboard/chat/page.tsx`
(historyView delegation); locales ×6; tests
(`ChatMessageList.logic.test.tsx` extension + new component tests + one hermetic
Playwright scenario "read history while streaming").

**Design:**
- `distanceToBottom(scroller) = scrollHeight - scrollTop - clientHeight`; threshold
  ~150 px; measured **at decision time** in the auto-scroll effect (recorded decision).
- Else-branch follow and end-of-stream scroll-to-user-message both run **only** when at
  bottom.
- Button visible when settled && !atBottom (rAF-throttled scroll listener for visibility
  only); in `historyView` it replaces the QW-2 banner semantics: label "return to
  present", `onClick = returnToPresent()` (disabled while `navInFlightRef` is busy);
  otherwise instant jump via the `pinToBottom` idiom (respects `prefers-reduced-motion`
  by being instant already).
- Badge: while a stream is active and the reader is away, show ↓ + count of assistant
  responses completed since leaving the bottom; one polite `aria-live` announcement per
  completed response; reset on reaching bottom (scroll or click).

**Edge-case register:**
- Initial pin window: button suppressed until the first successful pin (`justPositionedRef`)
  or the pin window expires — never flash the button during load positioning.
- Pagination prepend: scroll preservation untouched; button correctly visible (reader is
  up); `wasPrependRef` consumption order unchanged.
- Content growth without scroll events (images, lazy CodeBlock): live measurement at
  decision time covers it; visibility listener may lag one frame — cosmetic only.
- Mobile keyboard/viewport resize: live measurement; threshold generous.
- Click during active stream: jump, then follow resumes naturally (next decision measures
  at bottom).
- HITL interrupt mid-stream (no done chunk): badge increments on new assistant content
  ids, not on done — the interrupt card counts once.
- Proactive message arriving while away: no yank (guarded follow), badge increments.
- Empty conversation / conversation reload: state resets with the list.
- A11y: named button (i18n ×6), single aria-live region, focus never stolen.

**Regression guards:** **characterization suite first** (this is the program's
highest-regression lot): pin-at-open, prepend preservation, follow-at-bottom,
end-of-stream alignment — all pinned green before any behavioral edit; then the new
contract tests. Playwright hermetic proof.

---

### Lot 4 — A2: follow-up chips

**Goal:** 0–3 tappable follow-up suggestions under the latest assistant response,
generated by the Initiative node in the user's language, prefilling the input on click.

**Files (backend):** `nodes/initiative_node.py` (`followup_suggestions:
list[str] = Field(default_factory=list)` on `InitiativeDecision` + state write with
server-side dedupe/strip/truncate ≤3×200), `core/constants.py` + `agents/models.py`
(new declared state key `STATE_KEY_INITIATIVE_FOLLOWUPS`), `nodes/router_node_v3.py`
(reset with the sibling keys), `prompts/v1/initiative_prompt.txt` (instruct 0–3 short
follow-ups in `{user_language}`, produced even when `should_act=false`; keep the existing
`suggestion` semantics untouched), `nodes/initiative_recurrence.py` (verify passthrough —
it spreads `state_update`), create
`services/streaming/followup_handoff.py` (pop-once per-run cache, extraction_debug
pattern; same-process guarantee documented), `agents/api/service.py` (minimal call-site:
pop once **before** archival, feed both the archived `message_metadata` and
`done_metadata`), debug-panel surface (cache → emission → section; program rule),
Prometheus `initiative_followups_total` (emitted count).

**Files (frontend):** `types/chat.ts` + `types/chat-state.ts` (**both** DoneMetadata
types) + `reducers/chat-reducer.ts` mapping + `sse-symmetry.test.ts`; create
`components/chat/FollowupChips.tsx`; modify `chat/page.tsx` (render under the latest
assistant message; prefill callback) and `components/chat/ChatInput.tsx` (documented
`prefill: {text, nonce}` exception to the initializer-only contract; focus after
prefill); locales ×6 (group aria-label only — chip text is generated content);
`DebugPanel` section.

**Edge-case register:**
- Turn types without initiative (conversation route, skill turns, HITL-just-resolved,
  max-iterations, no adjacent tools): no key → chips absent; tolerated everywhere.
- ReAct mode: reached via `react_finalize` edge — covered; assert in an agents test.
- Cancelled runs (synthesized done) and HITL interrupts (no done chunk): absent key
  tolerated; archived-metadata path also absent — consistent.
- Initiative loop iterations: last write wins (state overwrite semantics — assert).
- Pop-once discipline: single pop feeding two consumers (archive + done) — double-pop is
  a bug class; unit-test the handoff (pop→empty; concurrent run_ids isolated).
- Suggestions containing markdown/HTML/newlines/duplicates/overlength: sanitized
  server-side; frontend renders as text children only (XSS boundary).
- Chip click with non-empty input: replaces content (recorded decision); input disabled
  (usage-blocked): chips hidden.
- Visibility: latest assistant message only && !isActiveStream && !historyView; reload
  shows them again while no newer turn exists (metadata rides `useConversation` spread —
  the latest-only condition implements "until a new turn").
- i18n: generated in `user_language` (prompt input exists); zh follows the backend
  canonical `zh-CN` upstream — no frontend keys for content.

**Regression guards:** initiative decision quality — the existing `suggestion` field,
skip logic and structured-output contract stay byte-compatible (OpenAI strict mode:
`extra="forbid"` respected — a defaulted list field is strict-safe like
`InitiativeAction.parameters`); prompt change reviewed against the golden/agents suites;
sse-symmetry + reducer + archived-metadata integration tests; SLOC: service.py gets
call-site lines only, logic lives in the new module.

---

### Lot 5 — B4: personalizable briefing grid

**Goal:** per-user visibility toggles + ordering for the 9 briefing cards; hidden cards
are neither fetched nor cache-read (real API/LLM economy); server-persisted preferences.

**Files (backend):** `users/models.py` (+`briefing_preferences` nullable JSONB) +
Alembic migration (upgrade/downgrade, single head, replay-check);
`briefing/schemas.py` (`BriefingPreferences {hidden: list[str], order: list[str]}`
validated against `SECTION_NAMES`, sanitizing reader for unknown names);
`briefing/router.py` (GET/PATCH `/briefing/preferences`; refresh endpoint rejects hidden
sections with a stable 400 code); `briefing/service.py` (`build_cards` skips hidden
`_section` calls → explicit placeholder status; `_iter_cards` /
`_read_cards_from_cache` / `_has_content` handle the placeholder — the three hidden
consumers); `briefing/constants.py` (placeholder status literal + error code).

**Files (frontend):** create `components/settings/BriefingGridSettings.tsx` (+ pure
`moveSection(list, from, to)` helper + tests); settings page wiring (`?section=`
compatible); `components/dashboard/TodayBriefing.tsx` (render from ordered visible
mapping section→component, staggerIndex from position, empty-grid CTA);
`hooks/useBriefingPreferences.ts`; locales ×6.

**Edge-case register:**
- No prefs (NULL column): all visible, canonical order — zero-migration behavior for
  existing users.
- All 9 hidden: grid renders a CTA line linking the settings; synthesis legitimately
  skipped (<2 threshold); greeting unaffected.
- Unknown section name in stored prefs (future removals): sanitized on read, never a 500.
- Future new section: completeness tests (backend registry == `SECTION_NAMES`; frontend
  mapping == section union) force registration; default = visible, appended at canonical
  position.
- Re-shown section within TTL: may serve cache up to its TTL (normal staleness, accepted).
- Reminders TTL=0 special case mirrored for the hidden path.
- `refetchSection('all')` skips hidden; direct refresh of hidden → 400 stable code.
- PATCH validation: unknown names 422; `order` sanitized to a permutation (dedupe,
  filter, append missing canonically).
- JSONB write = new dict; concurrent PATCH last-write-wins (single-user surface).
- `for_you` hidden with OPEN_LOOPS on: heartbeat unaffected (own repo access — verified).
- Reorder a11y: up/down buttons named with card title + position, `aria-live` announces
  the new position, focus stays on the moved row's button; DnD is pointer-only
  enhancement (buttons are the universal path).

**Regression guards:** characterization of current `build_cards` (all 9 fetchers called,
statuses propagated) before the skip logic; fetcher-not-called assertions (mock) for
hidden; migration replay-check; i18n parity; a11y ratchet.

---

### Lot 6 — A10: "getting started" checklist

**Goal:** dismissible dashboard card exposing dormant capabilities (7 detected items with
deep links), server-persisted dismissal/celebration, instance-flag-aware.

**Files (backend):** `users/models.py` (+`onboarding_checklist` nullable JSONB
`{dismissed_at, celebrated_at}`) + migration (replay-check); `/auth/me` response schema
(additive field); PATCH endpoint (display-mode-preference idiom); `/config` features
additive: `channels_enabled`, `heartbeat_enabled`, `skills_enabled`
(+`open_loops_enabled` here — shared mechanism with Lot 7, whichever ships first).

**Files (frontend):** create `components/dashboard/StarterChecklistCard.tsx` + exported
pure functions (`visibleItems(flags)`, `completion(states)`,
`shouldRender(prefs, completion)`, celebration transition); `TodayBriefing.tsx` insertion;
`useAppConfig` type extension; locales ×6.

**Items & detection (7):** provider connected (`useConnectorHealth`/connectors ≥1),
personality chosen (`usePersonality`), voice configured (voice prefs), Telegram bound
(`useChannelBindings`, flag-gated), heartbeat enabled (`useHeartbeatSettings`,
flag-gated), first space (`useSpaces`, rag flag), first automation
(`useScheduledActions`). Exact per-item predicates fixed in the lot plan.

**Edge-case register:**
- Never renders once `dismissed_at` or `celebrated_at` is persisted (reappearance never
  forced — the rule).
- Already-100% at first mount: silent `celebrated_at` persistence, no render (recorded
  decision — no retroactive noise for existing users).
- Live transition to 100%: discreet one-line celebration, then persist.
- Per-item hook error/404: item shows as not-done, card never crashes (per-item
  isolation, error boundaries at item level).
- Flags OFF: item absent, denominator shrinks; still fine with few items.
- Request cost: prefs ride `/auth/me` (zero extra); detection hooks mount only when the
  card is a render candidate.
- Later un-configuration (e.g., provider disconnected) with no persisted state: card
  reflects reality (may reappear) — consistent with the dismissal rule.
- JSONB new-dict on PATCH; multi-device consistency via server persistence.
- A11y: list semantics, `role="progressbar"` with `aria-valuenow`, links named; i18n ×6.

**Regression guards:** `/config` additive-only (pin existing keys in a test); `/auth/me`
schema additive; pure-function unit tests for every transition incl. the silent-celebrate
path.

---

### Lot 7 — B5: open-loops management view

**Goal:** lightweight consult/close surface for the commitments ledger — settings
section, grouped by direction, one-tap actions, closure metrics.

**Files (backend):** `open_loops/router.py` (close endpoint accepts optional body
`{action: "done" | "dismissed"}`, default `done`; maps to `closed_reason`
`api`/`dismissed`; 422 otherwise), `open_loops/repository.py` (docstring update only),
`observability/metrics_registry` (+`open_loop_closures_total{action}` emitted with
`suppress` at: router (done/dismissed), extractor conversational close, lazy expiry
(expired)), tests.

**Files (frontend):** create `components/settings/OpenLoopsSection.tsx` + pure
grouping/sorting helpers; `hooks/useOpenLoops.ts` (404-tolerant → section hidden);
settings nav entry gated on `/config.open_loops_enabled` (from Lot 6's mechanism — add
here if Lot 6 not yet shipped); `cards/ForYouCard.tsx` (loops heading links to the
section); locales ×6.

**Design:** `GET /open-loops?status=open`; two groups (user_owes / waiting_on_other);
sort `due_hint asc nulls last, created_at asc`; row = subject, counterparty, due badge
(browser tz, chat convention), days-open badge; actions: **Fait** (`done`), **Relancer**
(`chatDraftHref` + existing direction-aware intent keys), **Plus d'actualité**
(`dismissed`). No source column (arbitration 5). No manual creation.

**Edge-case register:**
- Flag OFF: nav entry hidden by config flag; hook additionally tolerates 404 (belt and
  braces for stale config cache).
- Empty state: encouraging line (the ledger fills itself — automatic value).
- Concurrent/already-closed: close returns 404 → restore optimistic row, info toast,
  refetch.
- `due_hint` null → no badge; overdue → accessible accent (not color-only).
- `counterparty` null; long subjects truncated with `title`.
- Cap 100: show "N shown" when at cap (no pagination v1, documented).
- Metrics cardinality bounded (4 actions); PII: subjects never at INFO (verify the
  existing `open_loop_closed` log fields in the lot session; fix to id-only if needed).
- i18n ×6 (incl. zh `_one` duplication for count keys); a11y: actions named with subject.

**Regression guards:** backend tests for action mapping/422/ownership-404/metrics;
extractor & expiry metric emission asserted; frontend grouping pure-function tests;
ForYouCard link is additive (existing tests untouched).

---

### Lot 8 — A4: slash commands

**Goal:** `/` at input start opens a filtered, keyboard-navigable, i18n'd command menu —
local commands (navigate/open search) and conversational commands (prefill only), plus
dialogue-skills loaded from the API.

**Files (backend):** `skills/router.py` — expose `dialogue` in `_merge_with_cache` and
`_skill_to_response` (+tests).

**Files (frontend):** create `lib/slash-commands.ts` (typed registry + pure
`filterCommands(query, commands)`), `components/chat/SlashCommandMenu.tsx` (WAI-ARIA:
wrapper `role="combobox"` `aria-expanded`, textarea `aria-autocomplete="list"`
`aria-controls` `aria-activedescendant`, menu `role="listbox"`/`option`);
modify `components/chat/ChatInput.tsx` (trigger detection `/^\/[a-z0-9-]*$/i` on the
first token, key interception ↑↓/Enter/Esc/Tab, A7-recall suppression guard);
`hooks/useSkills.ts` (`dialogue` on the `Skill` type); `chat/page.tsx` (local-command
callbacks: open search, navigate); locales ×6 (labels + descriptions for static
commands; skills use served localized `descriptions`).

**Commands v1:** `/resume` (conversational — prefills the literal `/resume`; arbitration
3), `/briefing` (local → dashboard), `/agenda` (conversational — localized intent),
`/recherche` (local → QW-2 search surface), dialogue-skills (conversational — localized
activation intent, ids namespaced `skill:<name>`).

**Edge-case register:**
- Menu open ⇒ ↑/↓ navigate options and A7 recall is suppressed (shared guard from Lot 2).
- `isComposing` ignored on every intercepted key (IME).
- A space after the command token closes the menu (`/resume extra` = normal text).
- Zero matches ⇒ menu auto-closes ⇒ Enter sends normally (recorded decision).
- Escape closes and keeps text; blur closes (option `onMouseDown` preventDefault so
  clicks land before blur); Tab closes without selecting.
- Skills list loading/error: static commands render immediately; skills appended when
  loaded; API error ⇒ static-only (no spinner in the menu).
- Disabled input (usage-blocked): no trigger (input disabled upstream).
- Long lists: listbox max-height + scroll, `aria-activedescendant` scrolled into view.
- Results-count announced via polite aria-live; focus never leaves the textarea.
- Paste of `/xyz`: trigger condition is value-shaped, not keystroke-shaped — deterministic.

**Regression guards:** exhaustive key-matrix component tests (Enter/Shift+Enter/↑/↓/
Esc/Tab × menu-open/closed × composing) written **before** wiring interception into the
send path; a11y roles/attrs asserted; backend exposure test.

---

### Lot 9 — A6: PWA (sub-lot 9a installability, sub-lot 9b share + hint)

**Goal 9a:** real installability on Android/desktop/iOS — PNG/maskable/apple icons,
per-locale manifests (lang/start_url), shortcuts, screenshots.

**Files 9a:** `public/` icons (icon-192/512, maskable-192/512, apple-touch-icon-180 —
generated from `icon.svg`, generation command documented, PNGs committed); 6 manifests
`public/manifest-{lng}.json` (per-locale `lang`, `start_url: /{lng}/dashboard`,
localized `name`/`shortcuts` (Chat, Briefing, Espaces — verify the spaces route in the
lot session), icons incl. separate maskable entries, `screenshots` wide+narrow);
`app/[lng]/layout.tsx`: convert static `metadata` → `generateMetadata({params})`
**preserving every field** (metadataBase, OG/Twitter, icons → PNG apple) + per-locale
`manifest`; vitest: manifest ×6 structural parity test + metadata snapshot test.

**Edge 9a:** browser manifest caching (bump filenames if iterating); maskable safe-zone
visual check; `zh` uses frontend-canonical `zh` locale codes in paths; scope kept at `/`
so cross-locale navigation stays in-app; theme_color consistent with the existing
`viewport.themeColor`.

**Goal 9b:** share text/URL into a prefilled chat + contextual install hint.

**Files 9b:** create `app/[lng]/share/page.tsx` (client page: compose
`title — text — url` → clamp at `CHAT_INPUT_MAX_LENGTH` → `router.replace(
chatDraftHref(lng, draft))`); manifests: `share_target` (GET, params title/text/url);
create `components/pwa/InstallHint.tsx` (PortraitHint pattern: pure visibility fn +
localStorage session counter ≥3 + dismissed-forever key; `beforeinstallprompt` capture
on Chromium; iOS Safari non-standalone variant shows "Add to Home Screen" instructions;
`display-mode: standalone` ⇒ never); `TodayBriefing` insertion; locales ×6.

**Edge 9b:** **unauthenticated share** must survive the login redirect with the full URL
(query included) — verify/extend the AuthProvider returnTo path (hard requirement);
empty/partial share params → plain chat; draft goes through the `?draft=` value path only
(textarea value — XSS-safe by construction); `beforeinstallprompt` never fires
(Firefox/iOS) → variant or nothing; hint shows once, dismiss is forever.

**Regression guards:** metadata snapshot before/after the `generateMetadata` conversion
(SEO); csp.test untouched (no header change); Lighthouse installability pass in the dev
container as runtime proof + manual Android/desktop install; iOS visual check.

---

### Lot 10 — B12: skills gallery + install-from-URL + channels

**Goal:** gallery UI (categories, detail sheet, provenance warning, preview), declarative
`channels:` metadata, and URL-source install feeding the existing hardened pipeline.

**Files (backend):** `skills/loader.py` (`EXTENSION_FIELDS["channels"] = None`;
validation: subset of `{text, frame, image}`, invalid ⇒ warn + None); generator
`validate_skill.py` parity (optional field, same rule); `skills/router.py` — expose
`channels` (+`category` already, +`dialogue` if Lot 8 not shipped) in both response
builders; create `skills/url_import.py`: `POST /skills/import-from-url {url}` —
**SSRF-hardened**: https only, resolve all A/AAAA and reject
private/reserved/loopback/link-local/multicast ranges, redirects disabled, connect+total
timeouts, **streamed** size cap, content sniffing (zip magic / markdown), then bytes →
`SkillImportService.import_upload` (zero bypass; S1–S4 + 409 apply);
settings module additions `SKILLS_URL_IMPORT_ENABLED` (default true),
`SKILLS_URL_IMPORT_MAX_BYTES`, `SKILLS_URL_IMPORT_TIMEOUT_SECONDS` (+ `.env.example`s —
parameterizable rule); rate limit settings-driven; Prometheus
`skill_url_imports_total{outcome}`; create `GET /skills/{name}/preview` streaming only
`assets/preview.png` (skill-name validation is the traversal guard; image content-type;
size cap; 404 fallback).

**Files (frontend):** refactor `components/settings/SkillsSettings.tsx` into a gallery
(new `SkillGallery.tsx`, `SkillDetailModal.tsx`, `ImportFromUrlDialog.tsx` — keep
`SkillsSettings` as the thin section shell to respect CC budgets); `useSkills.ts`
(channels/dialogue fields + `importFromUrl`); preview `<img>` with the attachments
crossOrigin idiom + fallback icon; provenance warning on every non-admin skill sheet and
in the URL-install confirm dialog; locales ×6.

**Edge-case register:**
- SSRF matrix unit tests: `http://`, `https://127.0.0.1`, `https://[::1]`, RFC1918,
  169.254.169.254, multicast, DNS-to-private; redirect attempts blocked. Residual
  DNS-rebinding risk documented (resolve-then-connect without IP pinning) — mitigations:
  https-only, no redirects, bounded read, optional allowlist noted as future hardening.
- Oversized body: streamed cap → 413-class error, temp cleanup.
- Timeouts, 404s, non-skill content: stable error codes → i18n'd toasts.
- Filename inference: URL basename; fallback by magic bytes (`.zip` vs `SKILL.md`).
- Name conflict 409 / quota / reserved prefixes: surfaced verbatim from the pipeline.
- Preview: missing ⇒ placeholder; oversized ⇒ capped; only `assets/preview.png` is ever
  served (no arbitrary paths).
- `channels: None` ⇒ display "text" with a "declared by the skill" tooltip.
- Sandbox invariants byte-untouched (CSP, iframe airlock, srcDoc).
- Import during cache reload: existing `invalidate_and_reload` semantics; concurrent
  same-name imports resolved by S2 (409).

**Regression guards:** pipeline passthrough test (mocked fetch → `import_upload` called
with identical bytes/filename semantics as the upload path); loader/generator/import
three-way parity test extended to `channels`; existing SkillsSettings behavioral tests
migrated, not weakened; runtime proof = real URL import in the dev container from a
controlled local HTTPS server + gallery browser check.

---

## Execution order & release notes

1. **Lot 1 PERSO** (may pair with Lot 2 in one session if gates pass early)
2. **Lot 2 A7** → 3. **Lot 3 A3** (chat core; Lot 3 gets the characterization-first
   session) → 4. **Lot 4 A2** (needs Lot 1's action row as the chips' anchor)
5. **Lot 5 B4** → 6. **Lot 6 A10** (shared preference-column groundwork; Lot 6 also adds
   the `/config` flags Lot 7 consumes)
7. **Lot 7 B5** (⚠️ prod value requires `OPEN_LOOPS_ENABLED=true` — flag activation is a
   user/release action, dev proof uses the dev `.env`)
8. **Lot 8 A4** → 9. **Lots 9a/9b A6** → 10. **Lot 10 B12**

Every lot is independently releasable and strictly additive: nullable DB columns with
down-migrations (Lots 5/6), flag- or data-presence-gated UI everywhere, no contract
breaks. Rollback = revert the lot's commits; no data migration is destructive.

---

## Status tracker

| Lot | Item | Status | Session | Evidence |
|-----|------|--------|---------|----------|
| 1 | PERSO action row | **DONE (code + gates + runtime)** | 2026-07-22 S2 | 2343 tests, tsc/lint clean, 3 ratchets hold (CC baseline LOWERED), browser proof 390px: in-flow row `Copier·👍·👎` at bubble bottom, no text overlay |
| 2 | A7 draft + ↑ | **DONE (code + gates + runtime)** | 2026-07-22 S2 | useInputDraft 9/9 + ChatInput 50/50 + auth 30/30; browser proof: F5-restore, clear-on-send, ↑ recall (caret end), `?draft=` priority + persisted at consumption |
| 3 | A3 scroll invariant | **DONE (code + gates + e2e runtime)** | 2026-07-22 S2 | lib 13/13 + button 4/4 + suite 2358; e2e 5/5 (2 new + 3 baseline); tsc/lint clean; 3 ratchets hold; coverage 62.7% |
| 4 | A2 follow-up chips | **DONE (code + gates + runtime)** | 2026-07-22 S2 | backend 10905 + lint/mypy clean; frontend suite + 3 ratchets + coverage; runtime: 3 FR chips on a places turn → click prefill (no send) → reload persistence + A7 draft interplay |
| 5 | B4 briefing grid | **DONE (code + gates + runtime)** | 2026-07-23 S2 | backend 10921 + mypy 947; migration b7e3d9c41a56 replayed (down+up); frontend 2390 + ratchets; runtime: PUT prefs → weather `hidden` (zero fetch) vs `not_configured` (fetch) both observed, hidden refresh 400, grid order flip on screen, settings 9 rows/switches |
| 6 | A10 checklist | **DONE (code + gates + runtime)** | 2026-07-23 S2 | migration c9f1a2b8d374 replayed; /config +4 flags; backend 10921 + mypy; frontend 2400 + ratchets; runtime: 7-item card 0/7, named FR links, dismiss → gone after F5 with server dismissed_at |
| 7 | B5 open loops view | **DONE (code + gates + runtime)** | 2026-07-23 S2 | backend 10923 + mypy 948; frontend suite + ratchets + coverage; runtime: seeded loops → Fait=closed_reason api, Plus d'actualité=dismissed (DB), `open_loop_closures_total{api,dismissed}=1` in /metrics, empty state after |
| 8 | A4 slash commands | **DONE (code + gates + runtime)** | 2026-07-23 S2 | backend 10926 + mypy; frontend 2432 + ratchets + coverage; runtime on .29: menu 5 options (4 static + real dialogue skill from API), filter, Enter→`/resume` prefill NO send, `/briefing` local nav + clear |
| 9a | A6 installability | **DONE (code + gates + runtime)** | 2026-07-23 S3 | pwa-manifests 10/10 (6-locale structural parity, SEO guard); icons/screenshots/apple-touch 200 on .29; `<link rel=manifest>` localized per page lang |
| 9b | A6 share + hint | **DONE (code + gates + runtime)** | 2026-07-23 S3 | share URL → chat draft prefill (never sent); InstallHint ≥3 visits + dismiss flag + gone (Flight-payload false positive documented); hooks-ratchet-clean rewrite (snapshot initializer + listener setState) |
| QA-R1 | page scrollbar regression | **DONE (fixed + proven)** | 2026-07-23 S3 | root cause: `sr-only` live region (absolute, no positioned ancestor) at thread end stretched BODY to 1341px; `relative` h-0 wrapper → docScrollH 800 = innerH |
| QA-R2 | trace into action row | **DONE (proven)** | 2026-07-23 S3 | disclosure now a fragment in AssistantActionRow: toggle `ml-auto` right-aligned next to Copy/👍/👎, panel wraps `w-full`; archived messages carry it too |
| QA-R3 | slash catalog enrichment | **DONE (proven)** | 2026-07-23 S3 | +6 conversational shortcuts (emails, weather, weather-weekend, tasks, reminders, news) ×6 locales; `/mete` filters via localized label alias; Enter prefills FR intent, no send |
| QA-R4 | journal/portrait English | **DONE (fixed + proven)** | 2026-07-23 S3 | root cause: portrait spec's English voice examples 150 lines below the weak lang line; prompts now bind {user_language} at generation point; real consolidation re-run → portrait full+brief in FRENCH in DB |
| QA-R5 | ↑/↓ sent-history walk | **DONE (proven)** | 2026-07-23 S3 | `useSentHistoryNavigation` (walk invariant by render-adjustment) + `sentHistoryOf` (lib, newest-first, consec-dedup, cap 10); browser: ↑↑↑ then ↓↓↓ back to empty |
| QA-R6 | telephony in admin connectors | **DONE (proven)** | 2026-07-23 S3 | `elevenlabs_telephony` in CONNECTOR_TYPES/LABELS/categories + admin section + i18n ×6; admin UI shows Téléphonie category with live status |
| 10 | B12 skills gallery | **DONE (code + gates + runtime)** | 2026-07-23 S3 | backend 10963 + lint clean; skills suite 200; frontend 2463 + 3 ratchets (CC gain locked, 52→51 files); runtime on .29: gallery 10 cards → detail modal (declared channels `texte`/`cadre interactif` from real frontmatter, preview 404 fallback, no provenance on admin), URL-import dialog (https-gated, provenance warning); REAL fetches: private IP → 400 `url_blocked`, HTML → 422, GitHub SKILL.md → 409 S2 pipeline, repo zip → 413 cap; all 4 outcomes in `skill_url_imports_total` |

## Session log

- **2026-07-23 — S3 (staged-code review + full remediation):** exhaustive inline
  review of the whole staged program (141 files). 3 medium + 9 low findings, ALL
  fixed same session:
  - **M1** `url_import`: httpx timeouts are per-phase → added the TOTAL transfer
    deadline (`asyncio.timeout`), slow-drip test; decomposed `_fetch_bytes` /
    `_read_bounded` when the backend CC ratchet (348>347) caught the grown function.
  - **M2** checklist PATCH now stamps on true TRANSITIONS only (idempotent replay —
    the docstring's contract); new test file pins it + the new-dict rule.
  - **M3** `settledRef` arms at pin-window expiry AND on user gesture — a short
    first exchange followed by a long answer now still gets the floating button.
  - **F1** per-user sliding-window rate limit on import-from-url (reuses the auth
    Redis limiter + fail-open policy; 2 settings + env examples; failed imports
    consume no skill quota, hence the dedicated window).
  - **F2** preview 404s for admin-disabled system skills (DB check added).
  - **F3** English-only API field descriptions; **F4** suppress justification
    comment; **F5** slash-menu highlight resets to the first option on re-filter
    (render-adjustment + discriminating test); **F8** chat-search focus targets its
    own `data-chat-search` marker; **F9** open-loops: 404 ⇒ unavailable, transient
    failures ⇒ retry affordance (hook contract extended + tests); **F6** e2e sleeps
    replaced by `expect.poll` on observable geometry (the 2 pin-window sleeps are
    structural — internal timer, documented); bonus: grid-settings a11y position
    announcement moved AFTER the successful persist.
  - **Deliberately NOT fixed (recorded debt):** the checklist's 6 live detection
    probes per dashboard visit while the card is a candidate. The proportionate
    fix is a backend aggregate endpoint (one query instead of six) — new API
    surface, out of a review pass's scope. Bounded cost: probes stop forever once
    dismissed/celebrated (at most a handful of visits).
- **2026-07-23 — S3 (Lot 10 B12, PROGRAM COMPLETE):** shipped per plan
  `plans/2026-07-23-uxr-lot10-b12.md` with one **recorded deviation**: the spec's
  `channels:` field already existed in the codebase as `outputs:` — the generator's
  `validate_skill.py` has always validated it (`VALID_OUTPUTS = {text, frame, image}`)
  and 8 system skills declare it; only the loader dropped it. Creating a parallel
  `channels:` would have forked the vocabulary, so the LOADER now surfaces `outputs`
  (EXTENSION_FIELDS + tolerant `_validate_outputs`, warn+None), parity-pinned against
  the generator (`SKILL_OUTPUT_CHANNELS` in constants). The verified-facts entry
  claiming "nothing declares them statically" is hereby corrected. SSRF: REUSED
  `agents/web_fetch/url_validator.validate_url` (hostname blacklist, DNS resolve,
  blocked ranges incl. IPv4-mapped IPv6) behind a strict https-only pre-check;
  redirects refused; streamed cap; magic-byte/frontmatter sniffing; stable `url_*`
  detail prefixes as the frontend toast contract. Endpoint feeds
  `SkillImportService.import_upload` verbatim (passthrough pinned by test).
  Preview endpoint serves ONLY `assets/preview.png` (name pattern = traversal guard,
  2 MiB cap, undifferentiated 404). Frontend: SkillsSettings decomposed into
  SkillGallery/SkillDetailModal/ImportFromUrlDialog + top-level handler factories
  (CC scanner aggregates nested closures into the nearest top-level function —
  extracting to an inner hook changes NOTHING; only top-level splits count; net CC
  gain locked, 52→51 files ≥15). Traps hit: F019 skip guard reads a bare
  `pytest.skip()` at function-body tail as PERMANENT (wrap it in `if script is None:`
  like the name-parity test); the useSkills test harness binds mutations BY
  DECLARATION ORDER (inserting a mutation shifts every later index); corrupted
  `.next/dev` webpack cache after double restart → JSON.parse 500s on every page
  (purge + restart, the recorded fix); the `:3000/api/v1` Next proxy path is
  dead-by-design in dev (http→https mismatch) — the frontend calls
  `NEXT_PUBLIC_API_URL` directly, so preview/upload URLs must use `apiBase()`.
  Gates: backend 10963 + `task lint` clean; frontend tsc/vitest 2463/coverage/
  3 ratchets/lint. Runtime proofs as per tracker. **All 10 lots + 6 QA remarks
  delivered — program closed pending user release.**
- **2026-07-23 — S3 (Lot 9 + QA remarks R1–R6):** Lot 9 finished after an
  InstallHint hooks rewrite (PortraitHint pattern: ONE `useState` env snapshot at
  render, write/subscribe-only effect, `canPrompt` state set in the
  `beforeinstallprompt` LISTENER — never read a ref in render, never setState in an
  effect body). The 1 failing coverage test was the `isPublicPath` completeness scan
  correctly catching the new `/share` route → classified public (transient redirect
  must never be ejected to login). Six QA remarks then landed mid-session, all
  delivered:
  - **R1 (regression, root-caused):** the Lot 3 `sr-only` live region is
    `position:absolute`; with NO positioned ancestor its static position (end of the
    message thread) escapes the scroller's clipping and stretches the BODY — the whole
    app grew a page scrollbar. Fix: zero-height `relative` wrapper as containing
    block. LESSON: any `sr-only` inside a scrollable region needs a positioned
    ancestor.
  - **R2:** ExecutionTraceDisclosure became a fragment hosted INSIDE
    AssistantActionRow (`ml-auto` toggle at the row's right edge, `w-full` expanded
    panel wrapping below). Archived messages carry the persisted trace, so history
    rows show it too.
  - **R3:** +6 everyday conversational shortcuts (emails/weather/weather-weekend/
    tasks/reminders/news), 18 i18n keys ×6; menu displays the stable id, localized
    label is the filter alias (Lot 8 design held).
  - **R4 (root-caused with DB evidence):** user `language='fr'` had an ENGLISH
    portrait — the consolidation prompt's "Write in {user_language}" (line 31) was
    overridden in practice by the portrait spec's English voice examples 150 lines
    below; the LLM copied "I notice…" verbatim. Fix: bind `{user_language}` at every
    generation point (voice line, brief spec, JSON schema) + strengthen introspection
    prompt. Proven end-to-end: container prompt reload + real consolidation call →
    portrait full+brief regenerated in FRENCH.
  - **R5:** ↑/↓ walk over the last 10 sends (`useSentHistoryNavigation`, invariant
    "index valid ⟺ input shows history[index] verbatim" maintained by render-phase
    adjustment; walk dies on edit; ↓ past newest lands on empty). `sentHistoryOf`
    extracted to `lib/sent-history.ts` (newest-first, consecutive dedup, cap
    `CHAT_SENT_HISTORY_MAX=10`).
  - **R6:** `elevenlabs_telephony` was missing from every frontend connector table
    (backend enum has it since telephony P1) → added to CONNECTOR_TYPES/LABELS,
    CONNECTOR_CATEGORIES, ADMIN_CONNECTOR_CATEGORIES + category/description i18n ×6.
    Admin section proven live (Téléphonie category, status from API).
  - CC ratchet regression (ChatInput 37>36 from one `??`) fixed by moving the default
    into the hook. Gates: tsc clean, vitest 2454 (then +6 tests), backend fast 10926,
    3 ratchets hold, i18n parity 0/0 ×5. False-positive trap documented: Next Flight
    `<script>` payload contains UI strings — never oracle on `document.body.textContent`
    for absence.
- **2026-07-22 — Program session:** exhaustive inline verification of the 10 briefs
  (4 corrections found: A2 single-suggestion, A3 missing invariant, A7 missing frontend
  cap, B5 source_ref/conversation-singleton), adversarial counter-pass (mobile
  breakpoint, graph edges, closed_reason constraint), 8 arbitrations signed off, this
  document written. No code touched.
- **2026-07-22 — S2 (Lot 1 PERSO):** action row shipped TDD-first (plan
  `plans/2026-07-22-uxr-lot1-perso.md`). **Recorded deviation** from the "Copy stays
  rendered mid-stream" micro-decision: the whole action row is hidden while
  `isActiveStream` — an in-flow row at the bubble's growing edge would jitter on every
  token (the old absolute button did not affect layout); hover-reveal dropped in favor of
  the always-visible interest pattern (an in-flow `opacity-0` row would reserve ghost
  space). CC ratchet initially regressed to 61 → fixed by extracting
  `AssistantActionRow` (net CC ↓, baseline locked lower). Boy Scout: `copied` timer now
  cleaned on unmount. Gates: 2329 tests, clean tsc, lint, coverage 62.6%, 3 ratchets.
- **2026-07-22 — S2 (Lot 2 A7):** draft persistence + ↑ recall shipped TDD-first (plan
  `plans/2026-07-22-uxr-lot2-a7.md`). Review pass caught a real hole: the consumed
  `?draft=` was stripped without ever being persisted (ChatInput never signals its
  initial value) → the consumption effect now hands it to `saveDraft`. CC ratchet
  regression (page 32→34) fixed by decomposition (`resolveInitialMessage`,
  `lastUserMessageOf`, hook takes the nullable user object). auth.tsx per-file coverage
  threshold (88% branches) enforced two new logout tests (purge + anonymous no-op).
  **Environment repair (pre-existing drift, again):** `.env` had reverted to
  `192.168.0.29` on all 8 browser-facing URLs while the host is `.30` → sed to `.30` +
  `docker compose -f docker-compose.dev.yml up -d --force-recreate api web` (the
  documented procedure; `docker restart` never re-reads `.env`). Runtime proof (QA
  account `uxr.qa@example.com` on the dev stack, Chrome via
  `https://192.168.0.30.nip.io:3000`): Lot 1 row layout mobile 390px + desktop, draft
  F5-restore, clear-on-send, ↑ recall with caret at end, `?draft=` priority + strip +
  persistence at consumption — all observed live.
- **2026-07-22 — S2 (Lot 3 A3):** reading invariant + floating button shipped
  (plan `plans/2026-07-22-uxr-lot3-a3.md`; design evolved during e2e-driven debugging —
  the plan's T1 own-send detection was replaced, see below). The gate-promise SSE e2e
  (`chat-scroll-follow.spec.ts`) caught THREE real defects unit tests could not:
  (1) **stale `justPositionedRef`** — the pin loop re-raised the one-shot flag every
  frame after its consumption; the stale flag swallowed the first post-load messages
  update (an own send never scrolled). Fixed at the root: `pinActiveRef` reflects the
  loop's real activity window (raised at start, lowered at expiry/gesture/cleanup).
  (2) **own-send detection by data diff is impossible** — the last-entry role check
  missed the batched SEND+STREAM_START render, and the last-user-id comparison
  false-fired when the post-`done` history reload swapped optimistic ids for server
  ids (yanking the reader). Final design: the page emits an explicit `ownSendTick`
  prop from `sendMessageFromPresent`.
  (3) **self-measuring smooth follow + batch growth** — a smooth follow read its own
  running animation as "away" and stranded the viewport; a single large token batch
  grew the DOM before the effect measured. Final design: follow = instant
  `pinToBottom` per batch; `isScrollerAtBottom(el, prevScrollHeight)` discounts the
  batch's growth (`prevContentHeightRef`). `messagesEndRef` became dead and was
  removed. CC: component decomposed (ScrollUiOverlay, EmptyConversation,
  OlderHistoryEdge, resolveScrollerOf, lastIdOf) — file back under every cap.
  QW-2 banner KEPT (recorded interpretation); button delegates `returnToPresent` in
  historyView. i18n `chat.scroll.*` ×6 (zh `_one` dupliqué). Evidence: e2e 5/5, suite
  2358, ratchets hold, coverage 62.7%.
- **2026-07-22 — S2 (Lot 4 A2):** follow-up chips shipped (plan
  `plans/2026-07-22-uxr-lot4-a2.md`). **Design correction during implementation:** the
  service's `state` variable is the PRE-RUN snapshot (load_or_create_state, never
  refreshed) — reading the new state key there would surface the PREVIOUS turn's chips
  → per-run pop-once TTL cache (`followup_metadata.push/pop_followups`, imitates
  open_loop_extractor). **Suspected latent staleness noted (out of scope):**
  `injected_journal_ids` (QW-5) is read from the same pre-run snapshot at
  service.py:1191 while response_node writes it during the turn — likely attributes the
  PREVIOUS turn's journal ids to the archived answer; to verify/fix separately.
  Gate lessons: prompt-cache hygiene guard rejects placeholders before the DYNAMIC
  marker (reworded without `{user_language}`); react-hooks ratchet forbids
  setState-in-effect → prefill uses the render-adjustment pattern inside a module-level
  `useControlledPrefill` hook (also keeps component CC flat); reducers carry a 100%
  branch threshold (three STREAM_DONE chips tests). Runtime proof (dev stack, real
  LLM): places turn → 3 French chips (contextually adapted to the missing connector),
  click → exact prefill, focus, caret end, NO auto-send; reload → chips persist via
  archived metadata AND the A7 draft restored (inter-lot interplay observed live).
  Evidence: backend 10905 + mypy 946 clean; frontend suite + 3 ratchets + coverage.
- **2026-07-23 — S2 (Lot 5 B4):** personalizable briefing grid shipped (plan
  `plans/2026-07-22-uxr-lot5-b4.md`). Backend: `CardStatus.HIDDEN`,
  `briefing/preferences.py` (strict schema + tolerant JSONB reader),
  `users.briefing_preferences` migration `b7e3d9c41a56` (replay proven down+up
  IN-CONTAINER — the replay-check script's docker probe is broken, and beware: a
  `docker exec … | tail` pipeline masks alembic's exit code, and killing blockers
  mid-ALTER also kills alembic's own session; open_loops dev data was dropped/recreated
  in the process), `_section`/`_read_section_cache` chokepoints (zero fetch/IO when
  hidden), refresh 400 `section_hidden` via `raise_invalid_input`.
  **Two pre-existing drifts fixed + PINNED:** `RefreshSectionLiteral` had 6 of 9
  sections (for_you/tasks/documents unrefreshable); default order now
  `SECTION_DISPLAY_ORDER_DEFAULT` (historical grid layout — SECTION_NAMES order would
  have silently reshuffled every user's grid). Completeness guard test:
  SECTION_NAMES == RefreshLiteral∖{all} == CardsBundle fields.
  Frontend: `useBriefingPreferences` (derived-with-override — NO state-sync effect,
  hooks ratchet caught it again), TodayBriefing renders via `CARD_RENDERERS` map +
  `visibleOrderedSections` (pinned), `BriefingGridSettings` (9 rows, switches, ↑/↓
  keyboard + DnD enhancement), i18n ×6. Runtime (QA account): PUT 200; hidden weather
  = `hidden` placeholder (no fetch) vs `not_configured` (real fetch) — both statuses
  observed proving the short-circuit; hidden refresh → 400; on-screen order flip
  (for_you before reminders); settings section shows 9 draggable rows.
  Note: QA account renders only 2 cards (connector-less `not_configured` self-hide) —
  full-grid visual check deferred to a connected account at release QA.
- **2026-07-23 — S2 (Lot 6 A10):** starter checklist shipped (plan
  `plans/2026-07-23-uxr-lot6-a10.md`). `/config.features` +4 additive flags
  (channels/heartbeat/skills/open_loops — B5 consumes them next); migration
  `c9f1a2b8d374` replayed up/down/up in-container; `UserBase.onboarding_checklist`
  additive; PATCH endpoint EXTRACTED to `auth/checklist_router.py` — the SLOC ratchet
  refused +26 lines on the frozen `auth/router.py` (858 > 832), exactly as designed.
  react-hooks ratchet hit a THIRD setState-in-effect (celebration) → render-adjustment
  derivation (`sawIncomplete` adjusted during render, effect is network-only); accepted
  micro-tradeoff documented: a fast pre-completed profile may see the discreet
  celebration line once (probes-loading counts as "incomplete seen"), celebrated_at
  caps it at once ever. Card body mounts (and probes) only while candidate.
  Runtime (QA account): 7 items (all flags on), 0/7, named FR links (connector →
  `?section=connectors`), dismiss → gone immediately AND after F5,
  `dismissed_at` visible in `/auth/me`. Evidence: backend 10921 + mypy 947; frontend
  2400 + 3 ratchets + coverage 63.4%.
- **2026-07-23 — S2 (Lot 7 B5):** open-loops management view shipped (plan
  `plans/2026-07-23-uxr-lot7-b5.md`). Metrics CHOKEPOINT in the repository
  (`close_loop` emits by closed_reason — covers API and conversational extractor in
  one site; `expire_stale` emits `expired` by count; suppress + comment idiom).
  `CloseLoopRequest {action: done|dismissed}` (conversational/expired rejected from
  the API by the Literal); repository docstring updated. Frontend:
  `useOpenLoops` (404-tolerant + optimistic derived-with-override removals),
  `OpenLoopsSection` in settings (arbitration 4a; gated on Lot 6's
  `open_loops_enabled` /config flag; no source column per 5a; no manual creation),
  Relancer reuses the ForYouCard direction-aware intents (`chatDraftHref`),
  ForYouCard loops heading now links to the settings. Runtime: 2 seeded loops →
  both direction groups rendered; Fait → `closed_reason=api` in DB; Plus
  d'actualité → `dismissed`; `open_loop_closures_total{action=api|dismissed}=1`
  scraped from /metrics; empty state shown after. Evidence: backend 10923 + mypy
  948; frontend suite + 3 ratchets + coverage.
- **2026-07-23 — S2 (Lot 8 A4):** slash commands shipped (plan
  `plans/2026-07-23-uxr-lot8-a4.md`). Backend: `dialogue` exposed in both skills
  response builders (+tests). Frontend: `lib/slash-commands.ts` (trigger = the whole
  value is the token; diacritic-insensitive filter on id+localized label),
  `useSlashMenu` + `SlashCommandMenu` (hand-built, arbitration 2a), ChatInput
  integration (menu owns ↑↓/Enter/Esc — suppresses A7 recall and send while open),
  page-built localized registry (4 static + dialogue skills). **A11y design
  correction from the gates:** `role="combobox"` on the textarea broke 34 tests
  (getByRole textbox) and would misdescribe the composer permanently; jsx-a11y also
  rejects `aria-expanded` on textbox → final wiring is ARIA 1.1-style
  (native textbox + aria-controls/activedescendant/autocomplete only).
  react-hooks ratchet counts ANY react-hooks/* ruleId — an exhaustive-deps warning
  regressed it (items memoized). Runtime (.29 origin — USER-DIRECTED: dev access is
  https://192.168.0.29.nip.io:3000, .env realigned .29 ×8 + force-recreate; both
  IPs answer on this host, .29 is the reference): menu with 5 options incl. the
  real `skill:skill-generator` dialogue skill from the API, `/res` filter → 1,
  Enter → `/resume` prefilled with zero message sent, `/briefing` → navigation +
  cleared input. Evidence: backend 10926 + mypy 948; frontend 2432 + 3 ratchets +
  coverage.

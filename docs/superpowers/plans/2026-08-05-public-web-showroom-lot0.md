# Public Web Showroom P0 Implementation Plan

> **For the implementing agent:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task by task, superpowers:test-driven-development for each behavior change, and superpowers:verification-before-completion before claiming a gate is green.

**Goal:** Replace the passive /demo page with an honest, deterministic, user-driven synthetic mission that demonstrates LIA's orchestration and approval UI contracts through a synthetic storyboard and simulation receipt, without implying live execution or invoking an agent, provider, connector, or new runtime service.

**Architecture:** Keep the landing animation unchanged. Add a client-only finite-state mission under a new components/showroom boundary, reuse HitlActionCard and ExecutionTraceDisclosure, and select the experience through one bounded Web build setting. Add a dedicated credential-less enum-only route in the existing product domain for aggregate showroom events; the mission remains usable when telemetry is disabled or unavailable.

**Tech stack:** Next.js 16, React 19, TypeScript 6, react-i18next, Vitest, Testing Library, Playwright, axe-core, and a dedicated route in the existing product telemetry domain.

**Program specification:** docs/superpowers/specs/2026-08-05-public-web-showroom-program.md

## Global execution constraints

- Never start, stop, inspect, query, or connect to an existing DEV or PROD service, container, database, Redis instance, provider, network, or volume.
- Unit, type, lint, and hermetic browser commands below are local-process checks. Playwright must own its temporary Web process and intercept every /api/v1 request.
- Perform no Git action. Each task ends with a suggested checkpoint message for the repository owner, not a commit command.
- Habits was released in v1.28.0 (`c5955b73`, 2026-08-05); the former dirty-worktree constraint is resolved. Still verify the worktree is clean before starting, and before modifying an existing file inspect its current state for any newer unrelated workstream.
- Repository prose is in English; user-visible copy is translated in all six locales.
- Persistent labels Guided, Synthetic data, and No external action are acceptance criteria. P0 is never described as live inference or as having sent an external action.
- No application telemetry event, application URL parameter, localStorage, sessionStorage, persisted reducer state, application event row, or application-managed log field contains visitor text, fixture text, email, fingerprint, IP-derived value, tool argument, or free-form decision content. A draft-edit field may hold transient controlled input until submit/cancel, then must clear it. This is an application-layer guarantee, not a claim of anonymous transport: the launch gate separately audits and discloses CDN, hosting, load-balancer, and reverse-proxy access-log behavior, disables or redacts it where supported, and forbids joining it to the showroom funnel.
- The only optional network activity of the mission itself is credential-less `POST /api/v1/product/showroom-events` when telemetry is enabled. Mission behavior must never call ordinary product events, chat, auth, connectors, tools, MCP, upload, WebSocket, or SSE routes. The layout-level `TelemetryBootstrap` (Web Vitals/PWA through the ordinary credentialed route) is a pre-existing shell emitter outside the mission: it is disclosed, excluded from the showroom funnel, and neutralized in the hermetic contract builds with `NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE=0`.

## Target file map

Create:

- apps/web/src/components/showroom/types.ts
- apps/web/src/components/showroom/fixtures/v1.ts
- apps/web/src/components/showroom/reducer.ts
- apps/web/src/components/showroom/hitl-adapter.ts
- apps/web/src/components/showroom/proof-links.ts
- apps/web/src/components/showroom/useShowroomMission.ts
- apps/web/src/components/showroom/ShowroomMission.tsx
- apps/web/src/components/showroom/ExecutionReceipt.tsx
- apps/web/src/components/showroom/ProofDrawer.tsx
- apps/web/src/components/showroom/__tests__/fixtures.test.ts
- apps/web/src/components/showroom/__tests__/reducer.test.ts
- apps/web/src/components/showroom/__tests__/hitl-adapter.test.ts
- apps/web/src/components/showroom/__tests__/proof-links.test.ts
- apps/web/src/components/showroom/__tests__/ShowroomMission.test.tsx
- apps/web/src/lib/showroom-config.ts
- apps/web/src/lib/__tests__/showroom-config.test.ts
- apps/web/e2e/smoke/public-demo-showroom.spec.ts
- apps/web/e2e/a11y/axe-public-demo-showroom.spec.ts
- apps/web/e2e/capture/public-demo-showroom.spec.ts
- docs/marketing/PUBLIC_SHOWROOM_LAUNCH_PLAYBOOK.md
- apps/api/src/domains/product/showroom_telemetry.py
- apps/api/tests/unit/domains/product/test_showroom_telemetry.py

Modify:

- apps/web/src/app/[lng]/demo/page.tsx
- apps/web/src/app/[lng]/__tests__/public-pages-cosmos.test.tsx
- apps/web/src/lib/product-telemetry.ts
- apps/web/src/lib/__tests__/product-telemetry.test.ts
- apps/web/e2e/a11y/axe-public-pages.spec.ts
- all six apps/web/locales/*/translation.json files
- apps/api/src/domains/product/constants.py
- apps/api/src/domains/product/router.py
- apps/api/src/core/config/product.py
- apps/api/src/core/constants.py
- apps/api/tests/unit/domains/product/test_product_constants.py
- apps/api/tests/unit/domains/product/test_product_router.py
- .env.example
- .env.prod.example
- apps/web/e2e/playwright.config.ts
- Taskfile.yml
- .github/workflows/ci.yml
- README.md
- docs/INDEX.md

Leave apps/web/src/components/landing/InteractiveChatMockup.tsx, its mockup folder, apps/api/src/domains/agents, Compose files, providers, connectors, and migrations unchanged.

## Fixed mission contract

The immutable fictional fixture contains exactly these facts: a 07:30 run tomorrow; an Atlas email proposing 09:30; an existing Atlas calendar event at 09:00; a quote task due before 10:00; and synthetic rain from 07:00 through 09:00. Its fixed translated request is equivalent to:

> Organize my morning tomorrow. I want to run, reply to Atlas, and send the quote. Prepare the changes, but do not touch anything without my approval.

The sequence reads inbox, calendar, tasks, and weather; detects the conflicts; prepares one email draft and one calendar proposal; asks for two independent decisions; and produces a simulation receipt. Email supports confirm/edit/cancel; calendar supports confirm/cancel because the reused tool-confirmation card has no editor. The canonical recording confirms the email and cancels the calendar change, but all six supported combinations must reach a truthful receipt.

## Task 1: Add the bounded rollout setting

**Files:** create showroom-config.ts and its unit test; modify the two environment templates.

1. Write a failing test for getPublicShowroomVariant(): absent, invalid, or legacy returns legacy; guided returns guided; the helper never throws.
2. Run:

~~~bash
cd apps/web && pnpm vitest run src/lib/__tests__/showroom-config.test.ts
~~~

Expected: module-not-found failure.

3. Implement a pure parser for NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT. Default both templates to legacy. Do not add DEMO_MODE or alter any API setting. Cross-workstream note: this variable and `NEXT_PUBLIC_SHOWROOM_PROOF_SHA` (Task 5) are new public build variables — the self-host installer activation plan (Task 3, B03 public-variable inventory) must classify both as hosted-site-only (empty/`legacy` in the generic prebuilt image), and the hosted telemetry-enabled release build is distinct from that generic GHCR image, which stays telemetry-off.
4. Rerun the test and require a pass.
5. Suggested owner checkpoint: feat(showroom): add bounded client-only rollout setting

## Task 2: Define the fixture and pure state machine

**Files:** create types.ts, fixtures/v1.ts, reducer.ts, fixtures.test.ts, and reducer.test.ts.

1. Test that fixtureVersion is overloaded-morning-v1; all email-like identifiers use example.invalid; there are exactly four read sources; no URL, key, local path, command, provider name, or Date.now-derived date exists; and the data is deeply readonly.
2. Define and test these exact bounded contracts:

~~~ts
type ShowroomPhase =
  | 'ready'
  | 'reading_sources'
  | 'planning'
  | 'email_decision'
  | 'calendar_decision'
  | 'receipt';
type ShowroomDecisionKind = 'confirm' | 'edit' | 'cancel';
type ShowroomActionId = 'email_reply' | 'calendar_adjustment';
~~~

3. Test START only from ready; ADVANCE through reading_sources and planning; email DECIDE then calendar DECIDE; RESTART from every phase; and ignored duplicate, stale, unknown, or out-of-order events.
4. Test all six supported decision combinations. Reject calendar edit as an invalid action. Email edit requires trimmed non-empty input at the view boundary, but state stores only the bounded marker edited, never free text.
5. Run the two tests and expect missing-module failures.
6. Implement a discriminated ShowroomEvent union and pure showroomReducer. It must not import React, i18next, timers, window, or telemetry.
7. Run the two suites twice and require identical passes.
8. Suggested owner checkpoint: feat(showroom): model deterministic synthetic mission

## Task 3: Reuse the existing HITL and trace contracts

**Files:** create hitl-adapter.ts and its test; reuse HitlActionCard.tsx and ExecutionTraceDisclosure.tsx unchanged.

1. Test pure adapters from decision phases to the existing HitlCardState: email uses draft_critique and exposes confirm/edit/cancel; calendar uses tool_confirmation and exposes confirm/cancel only. Type note: `HitlCardState.submittedAction` is `'confirm' | 'cancel' | null` — the `edited` state lives in the showroom reducer only, and after an edit the card renders as resolved/confirmed; never widen or cast the existing type.
2. Assert adapters expose fixed synthetic fields only and never serialize prompt, system_message, chain_of_thought, api_key, token, or the entire fixture as tool arguments.
3. Test a public ExecutionTrace with four localized-label slots, bounded categories, deterministic duration, and reasoning equal to the empty string.
4. Run the focused test and expect failure.
5. Implement only the adapters; translation occurs in the caller.
6. Run:

~~~bash
cd apps/web && pnpm vitest run src/components/showroom/__tests__/hitl-adapter.test.ts src/components/chat/__tests__/HitlActionCard.test.tsx src/components/chat/__tests__/ExecutionTraceDisclosure.test.tsx
~~~

Expected: all pass with no fork of either existing component.

7. Suggested owner checkpoint: feat(showroom): reuse HITL and structured trace contracts

## Task 4: Build the controller and accessible mission UI

**Files:** create useShowroomMission.ts, ShowroomMission.tsx, ExecutionReceipt.tsx, ProofDrawer.tsx, and ShowroomMission.test.tsx.

1. With fake timers and userEvent, test persistent honesty labels, the fixed non-editable request, four sources, trace, both decision cards, all decision actions, a truthful receipt, and restart.
2. Test that cancel explicitly means not applied and confirm means applied only to the synthetic workspace, never sent externally.
3. Test keyboard-only completion, focus movement to each new phase heading, one polite status region, and focus return after closing the proof drawer.
4. Under reduced motion, timed advance is disabled and explicit Continue buttons expose all non-decision phases.
5. Spy on fetch, EventSource, WebSocket, and connector clients; every interaction must leave them untouched.
6. Prove the component suite initially fails.
7. Implement useShowroomMission with useReducer, bounded timers, focus intents, and an injected bounded onEvent callback. Clear timers on unmount.
8. Use semantic section, ol, dl, and heading structures. Reuse the repository dialog primitive for the proof drawer.
9. Run the component suite and pnpm type-check; require both to pass.
10. Suggested owner checkpoint: feat(showroom): add accessible interactive mission and receipt

## Task 5: Bind proof links to an immutable source reference

**Files:** create proof-links.ts and its test; complete ProofDrawer.tsx; modify environment templates.

1. Test getShowroomProofLinks(sha): accept only a full lowercase 40-hex commit SHA; reject tags, branches, abbreviated SHAs, URLs, and everything else.
2. Accepted SHAs build fixed links under https://github.com/jgouviergmail/LIA-Assistant/blob/. Missing or invalid SHAs return repository-root links with isImmutable false, and the UI cannot say exact source.
3. Keep a code-owned registry covering routing, planner/orchestrator, HITL, trace capture, and the public fixture/test. Callers cannot add a URL or path.
4. Implement NEXT_PUBLIC_SHOWROOM_PROOF_SHA through this helper only. Leave the template value empty with explanatory text; release CI supplies the full source SHA. A separate display tag may be shown only after CI proves tag^{commit} equals that SHA, but proof URLs always use the SHA.
5. Each drawer entry distinguishes product-core evidence from P0-fixture evidence and warns that the link opens GitHub.
6. Run proof-link and component tests. Require immutable and fallback modes to pass.
7. Suggested owner checkpoint: feat(showroom): add version-bound proof drawer

## Task 6: Add a credential-less bounded showroom collector

**Files:** create `showroom_telemetry.py` and its tests; modify product constants/config/router and tests on API, the Web telemetry module/tests, environment templates, then wire the mission controller.

1. Add failing backend tests for these exact non-attributed showroom events:

~~~text
demo_viewed
demo_mission_started
demo_first_hitl_decided
demo_hitl_confirm
demo_hitl_edit
demo_hitl_cancel
demo_completed
demo_first_proof_opened
demo_source_clicked
demo_release_clicked
demo_install_guide_clicked
~~~

Each must have a description and belong to a dedicated `SHOWROOM_EVENT_TYPES` subset accepted only by `POST /product/showroom-events`. Unknown and free-form values remain 422. Ordinary product-event behavior remains unchanged.

2. Write route/service tests proving the showroom route has no optional-session dependency, ignores even a supplied `lia_session` cookie, never reads `Request.client`, `x-forwarded-for`, User-Agent, referrer, or any visitor-derived identifier, and always writes `user_id=NULL`, `run_id=NULL`, `channel="web_showroom"`.
3. Add fixed global minute/day Redis quota keys with no IP/bucket suffix. Missing Redis or quota failure returns `202` with all items dropped and a bounded aggregate metric; it never falls back to a raw-IP or fail-open write. Quota exhaustion may lose measurement but cannot affect mission state.
4. Update `ProductEventType` and add every new value to `PRODUCT_EVENT_DESCRIPTIONS` (the import-time completeness assert fails otherwise); no migration is required for the current string column (`product_events.event_type` is `String(32)`; the longest showroom name is 26 characters). The showroom types go into a new `SHOWROOM_EVENT_TYPES` set only: a dedicated test must pin `SHOWROOM_EVENT_TYPES ∩ (CLIENT_EVENT_TYPES ∪ ANONYMOUS_EVENT_TYPES) == ∅`, so the ordinary `/product/events` schema (`ClientEventItem._bounded_event_type` validates against `CLIENT_EVENT_TYPES`) keeps rejecting them with 422 even for authenticated callers — the showroom funnel cannot be polluted through the ordinary route. Add a setting/constant for global minute/day caps, not an IP-HMAC secret. Mount the showroom route inside the product router, which `src/api/v1/routes.py` already gates behind `product_analytics_enabled`; the launch checklist (Task 10) must state that the hosted telemetry-enabled release requires `product_analytics_enabled=true` on the API.
5. Add a dedicated Web `trackShowroomEvent` emitter that posts only the exact enum to `/api/v1/product/showroom-events` with `credentials: "omit"`, `keepalive: true`, and no `sendBeacon`. Existing authenticated telemetry keeps its current contract.
6. In the guided branch only, do not render the existing `TrackView`: it calls the ordinary authenticated product-event path. Instead, the showroom controller calls `trackShowroomEvent("demo_viewed")` once on mount. Emit `demo_mission_started` when a visitor actually starts each run, `demo_first_hitl_decided` on that run's first accepted decision, one category event per decision, `demo_completed` when that run first reaches receipt, `demo_first_proof_opened` on the first post-receipt proof open, and at most one destination-specific CTA event per completed run. A deliberate restart returns to ready and must produce a new `demo_mission_started` before another completion. The legacy branch retains its existing `TrackView(event="demo_started")` behavior until that branch is retired; it is outside the guided P0 network oracle.
7. The showroom emitter is fire-and-forget. Implement and test at-most-one client emission attempts across rerenders; do not claim delivery, retry, server idempotence, unique visitors, or exactly-once processing.
8. Never emit a cookie, run identifier, action ID, locale, fixture field, edit instruction, referrer, IP-derived value, or user text. Backend tests assert this boundary in the request schema, application event rows, and application-managed logs; they do not overclaim control of upstream network access logs. Dashboard ratios use the coherent aggregate attempt pairs defined by the program specification and label telemetry/global-quota loss as a limitation.
9. Add a launch checklist item that inventories the CDN/hosting/load-balancer/reverse-proxy access-log policy for this route, records retention and deletion controls, disables or redacts those logs where supported, discloses residual collection, and proves the infrastructure dataset is not joined to showroom events.
10. Run:

~~~bash
cd apps/api && .venv/Scripts/pytest tests/unit/domains/product/test_product_constants.py tests/unit/domains/product/test_product_router.py tests/unit/domains/product/test_showroom_telemetry.py -q
cd apps/web && pnpm vitest run src/lib/__tests__/product-telemetry.test.ts src/components/showroom/__tests__/ShowroomMission.test.tsx
~~~

Expected: all pass.

11. Suggested owner checkpoint: feat(product): measure credential-less showroom funnel

## Task 7: Integrate /demo without changing the landing animation

**Files:** modify demo/page.tsx and public-pages-cosmos.test.tsx; leave InteractiveChatMockup unchanged.

1. Mock the variant helper and both content components. Test that legacy renders only the current mockup plus its existing ordinary `TrackView`, while guided renders only `ShowroomMission` and never renders `TrackView`.
2. In both branches preserve the cosmos shell, metadata, localized route, and header/footer. In guided mode, `ShowroomMission` emits `demo_viewed` through `trackShowroomEvent` and emits `demo_mission_started` only from the Start action. No guided transition calls `trackProductEvent`.
3. Prove the guided test fails, then implement one narrow content branch in the page. Do not branch global layout, middleware, auth, or API configuration.
4. Run:

~~~bash
cd apps/web && pnpm vitest run 'src/app/[lng]/__tests__/public-pages-cosmos.test.tsx' src/components/landing/__tests__/InteractiveChatMockup.test.tsx
~~~

Expected: all pass and the landing animation contract remains unchanged.

5. Suggested owner checkpoint: feat(showroom): route demo page to guided mission behind flag

## Task 8: Add six-locale copy with strict parity

**Files:** all six translation.json files and their showroom consumers.

1. Add one showroom namespace in English: facts, phase headings, source labels, honesty labels, approvals, receipt states, proof explanations, GitHub/source CTA, beta CTA, restart, Continue, and accessibility names.
2. Run task lint:i18n and require a failure listing the five missing locales.
3. Translate semantically into French, German, Spanish, Italian, and Chinese. Preserve exact key parity; duplicate Chinese _one where the repository parity rule requires it.
4. Rerun task lint:i18n and the component suite. No raw showroom key may render.
5. Suggested owner checkpoint: feat(i18n): translate public showroom mission

## Task 9: Prove hermetic behavior, responsive layout, and accessibility

**Files:** create the two E2E specs; modify `playwright.config.ts`, `Taskfile.yml`, `.github/workflows/ci.yml`, and the existing public-page axe spec.

1. Record every browser request. With product telemetry disabled in a clean managed production build, completing the mission must produce zero `/api/v1`, chat, auth, connector, tool, MCP, upload, WebSocket, or EventSource request. Do not mock a chat route; invocation must fail loudly.
2. Parameterize the managed-server configuration so `NEXT_PUBLIC_PRODUCT_TELEMETRY` is injected into the build environment, not only the Playwright test process. Add two sequential Task targets/CI invocations, each removing the managed `.next` output before build: one with `false`, one with `true`. Both builds also inject `NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE=0`: the layout-level `TelemetryBootstrap` (mounted for every page, `/demo` included) flushes Web Vitals to the credentialed `/api/v1/product/events` on visibility change when sampled, which would make the telemetry-enabled oracle either flaky or falsely green. Add one unit test asserting that `TelemetryBootstrap` is the only non-showroom emitter reachable from the demo page and that it is inert when `NEXT_PUBLIC_PRODUCT_TELEMETRY` is not `'true'`. They may not reuse an already running Web server or build artifact.
3. In the enabled build, intercept only credential-less `POST /api/v1/product/showroom-events`, assert that the browser request carries no `Cookie` or authorization header, validate the exact bounded schema/event names, return the real API contract `202`, and fail on every other API method/path plus every chat/SSE/WebSocket/connector request.
4. At 390x844, complete the canonical confirm-email/cancel-calendar path, one email-edit path, one all-cancel path, keyboard-only completion, and reduced-motion completion. Assert one mission-start attempt per explicitly started run and coherent first-decision/completion attempts after restart.
5. Check overflow at 320, 375, 390, 768, 1024, and 1280 px; sweep all six locales at 390 px; check light and dark.
6. Axe-scan ready, email decision, open proof drawer, and receipt in both themes. Critical and serious findings block.
7. Update the old decorative `role="img"` demo oracle to a mission-heading oracle under guided, retaining one legacy-path test.
8. Run only the repository E2E harness-managed temporary Web project. If its command would target an already-running server, stop and configure the documented ephemeral local Web process; never reuse DEV or PROD.
9. Expected: both clean builds pass, no unexpected request, only the allowed credential-less bounded telemetry request in the enabled scenario, no blocking axe issue, and no `scrollWidth` greater than `clientWidth`.
10. Suggested owner checkpoint: test(showroom): prove hermetic accessible public mission

## Task 10: Create reproducible launch assets and truthful claims

**Files:** create the capture spec and launch playbook; modify README.md and docs/INDEX.md.

1. The capture spec follows the canonical path at 1440x900 with a fixed clock and produces a sub-60-second mission, a 15-second approval/refusal excerpt, a proof screenshot, and a receipt screenshot in Playwright output, not automatically in Git.
2. The launch playbook uses this positioning: “LIA turns a personal intention into controlled action, shows what it did, respects every refusal, and can be self-hosted.”
3. It discloses guided/synthetic limits, supplies the canonical request, asset variants, UTM convention, publishing order, response ownership, and the quantitative P0-to-P2 gate. Discord is optional discussion/support, never execution.
4. README links the showroom and current setup docs, but does not promise one-command installation until the installer acceptance plan is green.
5. Index the program spec, plan, and playbook.
6. Run `task lint:docs`, the repository's formatting/whitespace gate, and a bounded text search for live AI, real inference, one command, and docker compose up. Any match must be a warning against the claim, not promotional copy.
7. Suggested owner checkpoint: docs(showroom): add truthful launch and proof playbook

## Task 11: Run the P0 release gate

1. Verify the worktree is clean (the Habits workstream was reconciled and released in v1.28.0). Do not run or interpret broad suites while overlapping files are changing in any concurrent workstream.
2. Run focused checks:

~~~bash
cd apps/web && pnpm vitest run src/components/showroom src/lib/__tests__/showroom-config.test.ts src/lib/__tests__/product-telemetry.test.ts 'src/app/[lng]/__tests__/public-pages-cosmos.test.tsx'
cd apps/api && .venv/Scripts/pytest tests/unit/domains/product/test_product_constants.py tests/unit/domains/product/test_product_router.py tests/unit/domains/product/test_showroom_telemetry.py -q
task lint:i18n
~~~

3. Run pnpm type-check, pnpm lint, and pnpm test in apps/web.
4. Run both sequential clean-build showroom Task targets (telemetry off, then on) plus the existing public axe and overflow suites; CI delegates to the same Task targets through the repository parity pattern.
5. Release CI builds with NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=guided and NEXT_PUBLIC_SHOWROOM_PROOF_SHA set to the full 40-character source SHA. No fake value is committed. If a release tag is displayed, CI resolves tag^{commit} and requires it to equal the supplied SHA.
6. Inspect every SHA-based proof URL in CI and require HTTP 200. This is source-link verification, not a call to DEV or PROD.
7. Promote guided only if every P0 gate in the program specification is green. Rollback is a Web rebuild with legacy; no backend or data rollback is involved.
8. Suggested owner checkpoint: feat(showroom): complete client-only public demo P0

## Completion definition

P0 is complete only when every supported decision path can be completed, synthetic limits remain unmistakable, refusals are visibly respected, the storyboard trace contains no reasoning, source links are truthful, and GitHub is reachable without any agent or external action dependency. Six-locale parity, keyboard and reduced-motion completion, axe, responsive overflow, coherent bounded best-effort event attempts, full-SHA proof references, telemetry-disabled and telemetry-enabled network oracles, and the fail-loud zero-agent-call oracle must all pass.

Completion does not authorize P2. Collect at least 14 full days and at least 500 starts, then apply the explicit go/no-go thresholds in the program specification.

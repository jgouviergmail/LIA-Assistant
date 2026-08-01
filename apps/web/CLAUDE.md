# CLAUDE.md — apps/web (frontend)

Scoped guidance for the Next.js frontend. The root `CLAUDE.md` (including its Systemic Rules) still applies; this file adds the frontend-specific invariants.

## Stack & validation

- Next.js 16 (App Router), React 19, TypeScript strict, Tailwind, react-i18next, vitest.
- Tests: `task test:frontend` (or `pnpm test` from `apps/web/`). Lint/format: `task lint:frontend` / `task format:frontend`.
- **Never validate runtime behavior with a local `pnpm build`/`pnpm dev` outside the workflow** — runtime validation goes through the Docker dev container (`lia-web-dev`). Static validation uses `task lint:frontend`; when types, tests, `tsconfig`, or generated declarations change, also run the clean host check `pnpm exec tsc --noEmit --incremental false` so a stale incremental cache cannot mask diagnostics. The pre-commit hook runs `eslint`, `tsc` and the i18n parity check from the host.
- After any `pnpm add`/`pnpm remove` inside the container, re-sync the host lockfile (root `CLAUDE.md` → Dev Container Pitfalls #1) or the prod build breaks on `--frozen-lockfile`.

## Audit quality gates (security excluded)

The root audit-derived gates apply in full. This section adds the frontend-specific contract; it introduces no security criterion.

- **Accessible interaction is correctness**: prefer native `button`, `a`, `label`, and form controls; give every control a stable translated programmatic name. Test keyboard activation, focus order/visibility/return, disabled/error states, dialogs, and announcements by role/name. Never replace native semantics with a generic key handler or suppression.
- **Tests stay type-safe and behavioral**: builders take `Partial<Props>` and return `Props` without `as any`, double assertions, `as never`, or ignored diagnostics; mocks preserve public signatures. Assert visible state, data transitions, requests, cancellation, and recovery. CSS selectors, snapshots, and fully mocked hooks cannot be the sole oracle for business behavior.
- **Ratchets are shrink-only**: coverage, `a11y`, React-hooks, and complexity baselines may only improve. Never exclude business code, disable a rule, relocate branches, or raise a baseline to pass. A touched violation should decrease before its baseline is updated.
- **Keep React logic explicit**: reducers are pure; derive state during render; effects synchronize external systems; clean up timers/listeners/streams and abort requests. Extract hotspots into typed state machines, hooks, decision tables, and pure functions — never a god-hook.
- **A refresh is not a first load, and a busy control is not a removed one.** Two ways a section silently destroys the user's work, both found in the same component (`PeerConnectionsSettings`, 2026-07-31): (1) `loading ? <Spinner/> : content` unmounts the subtree on every post-mutation refetch, wiping typed input and results — gate the spinner on a *first-load* flag that is monotone (derived from `data === undefined`, never from `error`, which a refetch resets), and announce refreshes with `aria-busy`; (2) putting `disabled` on a control **while it holds focus** makes the browser blur it and drop it from the tab order, so a keyboard user lands back on `<body>` — use `aria-disabled` plus a guard in the handler (the guard, not the attribute, is what prevents the double submit). Both cost a real user their place; both are invisible to a snapshot test and need a focus/value oracle.
- **Coverage follows risk**: prioritize localized App Router pages, chat/SSE reconnect/cancel, settings, connectors, Journals, spaces/uploads, voice/audio, retries, partial failures, cache invalidation, i18n, and timezone boundaries over trivial wrappers.
- **Browser assurance stays hermetic**: intercept controlled API/SSE traffic; never contact production, a real backend, or a paid provider. Changed critical journeys cover success, their highest-risk failure/retry, and keyboard/focus. Keep PR Chromium smoke fast; extend periodic evidence to Firefox/WebKit, zoom/reflow, contrast, and NVDA/VoiceOver.

From the repository root, run the complete local frontend gate after any behavioral change:

```bash
task lint:frontend
cd apps/web
pnpm exec tsc --noEmit --incremental false
pnpm test:coverage
pnpm a11y:ratchet && pnpm react-hooks:ratchet && pnpm cc:ratchet
```

Run the affected Playwright scenarios when a user journey changes; run the full hermetic E2E package when shared routing, API interception, accessibility infrastructure, or global layout changes.

## Security invariants (do not weaken)

- **BFF auth**: authentication is a HTTP-only session cookie sent via `credentials: 'include'` in `src/lib/api-client.ts`. **Never** store tokens/secrets in `localStorage`/`sessionStorage`; never add an `Authorization` header; never expose session material to JS.
- **XSS boundary**: any dynamic content (LLM output, API data, user input) is rendered either as React children (auto-escaped) or through the ReactMarkdown pipeline with the exact plugin order `[rehypeRaw, [rehypeSanitize, sanitizeSchema], rehypeMathInText, rehypeKatex]` (`src/lib/markdown-sanitize-schema.ts` — everything after sanitize is the math-rendering stage, sanitize-exempt on purpose). `rehypeMathInText` (`src/lib/rehype-math-in-text.ts`) converts `$…$`/`$$…$$` found in the raw HTML the assistant emits into KaTeX markers — needed because `remark-math` only sees markdown, not the HTML blocks the assistant wraps every answer in; it reads only already-sanitized text and emits fixed-class `<span>`s, so the XSS posture is unchanged.
- `dangerouslySetInnerHTML` is reserved for **app-controlled static content compiled from the repo** (blog/FAQ/guides markdown, JsonLd SEO). It is **never** used for LLM output, API payloads, or anything user-derived — when in doubt, render as children.
- MCP App / Skill App HTML renders **only** inside the sandboxed widget iframe (sentinel → widget), never through markdown.
- **CSP is per-document and test-pinned** (ADR-098): both policies live in `src/lib/csp.ts` and every feature-bearing directive is pinned by `src/lib/__tests__/csp.test.ts` — change policy and test together, never the header strings inline in `next.config.ts`. MCP App widgets render through the airlock shell (`public/widget-frame.html`, permissive CSP, sandbox = the real isolation); the shell's sandbox/lock logic must never be weakened (an unsandboxed shell executing a payload = XSS under the app origin). Skill `frame.html` widgets stay on `srcDoc` on purpose.

## Conventions

- **API access**: components never call `fetch` directly — use the typed hooks `useApiQuery`/`useApiMutation` (which wrap `api-client`). New feature → new hook in `src/hooks/use{Feature}.ts`.
- **Routing**: all pages live under `app/[lng]/` — every route is localized.
- **i18n**: keys in `locales/{lng}/translation.json`, 6 languages (en, fr, de, es, it, zh), **strict key parity enforced by the pre-commit hook** (`en` is the reference). zh has no CLDR plural form: duplicate the value to `_one` so parity passes. Backend contracts should ship structured data + `label_key`s resolved client-side — never pre-translated strings baked into API payloads.
- **Chat state**: `src/reducers/chat-reducer.ts` is a pure, immutable FSM (idle → sending → streaming → idle) with documented transitions and anti-race guards — no side effects in reducers, clear stale sub-state on transitions, add a reducer test for every new action.
- **Bundle discipline**: heavy components are lazy-loaded via `next/dynamic` (follow `McpAppWidget`, `SkillAppWidget`, `CodeBlock`/Prism, `MermaidDiagram`). Don't import them statically from shared paths.
- **TypeScript discipline**: `@ts-ignore`/`@ts-expect-error` are effectively forbidden (2 occurrences across 438 files — keep it that way); every `eslint-disable` carries a justification comment.
- **Timers/aborts**: prefer `AbortSignal.timeout()` over manual `setTimeout` + `AbortController`; always clean up timers and subscriptions in effects.
- **Diagrams in guides**: fenced ```mermaid blocks rendered by `MermaidDiagram` (dark-mode aware) — no ASCII art, no static images for flows.

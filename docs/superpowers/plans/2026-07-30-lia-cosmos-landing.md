# LIA Cosmos Landing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement
> this plan task-by-task, INLINE (owner rule: no subagents). Steps use checkbox (`- [ ]`)
> syntax for tracking. Owner rule: **no git commits** — "commit" gates are replaced by
> "checkpoint" gates (all listed checks green + inline code review).

**Goal:** Ship the validated "LIA Cosmos" identity as a dev-only parallel landing
(`/[lng]/cosmos`) reusing 100 % of the real landing content, then extend to /more, /demo
(Lot B) and the calm reading variant (Lot C).

**Architecture:** A `.cosmos` CSS scope (tokens + skins) plus small client primitives
(`CosmicBackdrop`, `GhostWord`, `GlowCard`, `BlurReveal`, `PinnedScene`, one shared rAF
scroll hook). Real sections are reused verbatim; only skin wrappers and two cosmos-specific
compositions (hero with planetarium, pinned day) are new. Swap = applying the scope to `/`.

**Tech Stack:** Next.js 16 App Router, React 19, TS strict, Tailwind + scoped vanilla CSS,
vitest + testing-library. **Zero new dependency.**

## Global Constraints (from spec, verbatim)

- Palette: blue `#4F8DFD` → violet `#8B5CF6` → cyan `#38D4F5` on near-black `#06070F`.
- Ghost words: translated i18n keys, size `clamp(7rem, 28vw, 26rem)`, `aria-hidden`,
  clipped, drift transform-only, none under reduced-motion.
- Animations: `transform`/`opacity` only; no continuously animated blur; one shared rAF.
- "One animation = one product idea" — no decorative-only motion.
- All existing i18n keys reused; new keys in **all 6 locales** (zh duplicates `_one`).
- Existing landing route byte-identical until swap; coverage guard test keeps passing.
- Preview routes `notFound()` in production; no `AuthRedirect`, no `TrackView` on previews.
- Reduced-motion: durations AND delays zeroed; final states shown.
- Sticky: never reintroduce a scrollport ancestor (ADR-171); e2e measures during scroll.
- Gates per checkpoint: `task lint:frontend` + `pnpm exec tsc --noEmit --incremental false`
  + `pnpm test` (scoped run during tasks, full at checkpoints). No commit, no push.

---

### Task A1: Cosmos scope CSS (tokens, layers, skins)

**Files:**
- Modify: `apps/web/src/styles/globals.css` (append one delimited `/* === LIA COSMOS === */` block)

**Interfaces:**
- Produces CSS classes consumed by later tasks: `.cosmos`, `.cosmos-ghost`,
  `.cosmos-glass`, `.cosmos-grad-text`, `.cosmos-rise`, `.cosmos-planet`, `.cosmos-orbit`,
  `.cosmos-eyebrow`, plus skin overrides for `.cosmos .landing-section`.

- [ ] Read the existing landing/theme blocks of `globals.css` (tokens, `.landing-page`,
  `.landing-section`, scroll-stage keyframes) to anchor naming and avoid collisions.
- [ ] Append the cosmos block. Source of truth for every value: the validated mockup
  `scratchpad/lia-cosmos-maquette.html` (v4). Transformation rules (exact):
  - every mockup `:root` token becomes `.cosmos { --cosmos-* }`;
  - light overrides move from `:root[data-theme="light"]` to `html:not(.dark) .cosmos`;
  - every mockup class gains the `cosmos-` prefix and is nested under `.cosmos`;
  - ghost size becomes `clamp(7rem, 28vw, 26rem)` (owner: larger);
  - the mockup's `body { overflow-x: clip }` is NOT copied (already global via ADR-171);
  - reduced-motion kill block copied verbatim (durations + delays zeroed) scoped to `.cosmos`.
- [ ] Skin overrides so reused sections restyle without edits (exact selectors):
  `.cosmos .landing-section { background: transparent; border-color: var(--cosmos-line); }`,
  `.cosmos .landing-section.bg-card`-equivalents via `.cosmos [class*="bg-card"]`? — NO:
  Tailwind utilities can't be wildcarded; instead override the two tinted section ids
  (`.cosmos #basics, .cosmos #transparency, .cosmos [id^="chapter-"]` backgrounds) and card
  surfaces `.cosmos .rounded-2xl.border` → glass via a dedicated rule list enumerated in the
  task (borders `var(--cosmos-line)`, bg `var(--cosmos-glass)`, `backdrop-filter: blur(14px)`).
- [ ] Checkpoint: `task lint:frontend` green (stylelint none — CSS passes prettier),
  `pnpm test` unaffected (no behavior change yet).

### Task A2: shared scroll loop hook

**Files:**
- Create: `apps/web/src/components/landing/cosmic/useCosmosScroll.ts`
- Test: `apps/web/src/components/landing/cosmic/__tests__/useCosmosScroll.test.ts`

**Interfaces:**
- Produces: `useCosmosScroll(callback: (scrollY: number) => void): void` — registers ONE
  passive scroll+resize listener, rAF-throttled, fires once on mount, cleans up on unmount.
  Also exports `clamp01(v: number): number` and
  `sectionProgress(rect: {top: number; height: number}, viewportH: number): number`
  (`clamp01((viewportH - top) / (viewportH + height))`) — pure, unit-tested.

- [ ] Write failing tests: `sectionProgress` returns 0 when section below viewport
  (top = viewportH), 1 when fully past (top = -height), 0.5 at symmetric middle; `clamp01`
  clamps; hook registers and removes listener (spy on add/removeEventListener), fires
  callback on mount.
- [ ] Run: `pnpm vitest run src/components/landing/cosmic/__tests__/useCosmosScroll.test.ts` → FAIL.
- [ ] Implement (rAF via `requestAnimationFrame` guarded by a `ticking` ref; passive: true).
- [ ] Re-run → PASS.

### Task A3: CosmicBackdrop + dead-code removal

**Files:**
- Create: `apps/web/src/components/landing/cosmic/CosmicBackdrop.tsx`
- Delete: `apps/web/src/components/landing/ConstellationBackground.tsx` (unwired dead export)
- Modify: `apps/web/src/components/landing/index.ts` (remove the dead re-export)
- Test: `apps/web/src/components/landing/cosmic/__tests__/CosmicBackdrop.test.tsx`

**Interfaces:**
- Produces: `<CosmicBackdrop />` — client component, renders `aria-hidden` fixed layers:
  nebula div, grain div, `<canvas>` stars drawn once (≤180, width-capped, DPR-capped 2,
  redraw only on debounced resize). No scroll work.

- [ ] Failing tests: renders canvas + layers all `aria-hidden`; draws once on mount (spy
  `getContext('2d')` mock); reduced-motion adds no listener beyond resize; unmount clears
  the resize timer (vi.useFakeTimers, no post-unmount setState warnings).
- [ ] Implement; grep repo for remaining `ConstellationBackground` references → none.
- [ ] Run cosmic tests + `pnpm vitest run src/components/landing` → PASS.

### Task A4: GhostWord

**Files:**
- Create: `apps/web/src/components/landing/cosmic/GhostWord.tsx`
- Test: `apps/web/src/components/landing/cosmic/__tests__/GhostWord.test.tsx`

**Interfaces:**
- Produces: `<GhostWord wordKey="landing.cosmos.ghost.act" direction={1|-1} high?>` —
  client component; `useTranslation()`; renders `<span aria-hidden className="cosmos-ghost">`;
  drift = `(sectionProgress − 0.5) × viewportW × 0.24 × direction` applied as
  `translate(xpx, -50%)` via `useCosmosScroll`, measuring `ref.parentElement.closest('section')`;
  no transform writes under `prefers-reduced-motion`.

- [ ] Failing tests: renders translated text, `aria-hidden="true"`; direction −1 yields
  negative x when progress > 0.5 (mock getBoundingClientRect + fire scroll); reduced-motion
  (matchMedia mock) leaves `style.transform` empty.
- [ ] Implement → tests PASS.

### Task A5: GlowCard + BlurReveal

**Files:**
- Create: `apps/web/src/components/landing/cosmic/GlowCard.tsx` (server-safe: pure classes)
- Create: `apps/web/src/components/landing/cosmic/BlurReveal.tsx` (client, IO one-shot)
- Test: `apps/web/src/components/landing/cosmic/__tests__/reveal.test.tsx`

**Interfaces:**
- Produces: `<GlowCard tilt?: -2|-1|1|2 className?>` → div `.cosmos-glass` (+
  `.cosmos-tilt-{n}`); `<BlurReveal delay?: number>` → wrapper `.cosmos-reveal`, adds
  `.in` when intersecting (threshold 0.25, unobserve after), `style.transitionDelay` from
  prop; reduced-motion → `.in` immediately.

- [ ] Failing tests (mirror existing `ScrollStage` test patterns): IO callback adds `.in`
  once and unobserves; delay prop sets transitionDelay; reduced-motion renders `.in` on
  mount; GlowCard merges className.
- [ ] Implement → PASS.

### Task A6: PinnedScene

**Files:**
- Create: `apps/web/src/components/landing/cosmic/PinnedScene.tsx`
- Test: `apps/web/src/components/landing/cosmic/__tests__/PinnedScene.test.tsx`

**Interfaces:**
- Produces: `<PinnedScene heights={3.2} disabled={bool} children>` — renders
  `<div className="cosmos-pin" style={{height: `${heights * 100}vh`}}>` containing
  `<div className="cosmos-pin-stage">` (sticky). Exposes progress by setting `--p` (0..1,
  from `-rect.top / (height − viewportH)`) on the outer div via `useCosmosScroll`.
  `disabled` (mobile <760 px via matchMedia, or reduced-motion, or prop) renders children
  in normal flow (no sticky, no vars). Children read `--p` with CSS or via
  `usePinProgress()` context (exported: `PinProgressContext: React.Context<number>` set on
  each frame — NO, context per frame re-renders; instead children read the CSS var or
  subscribe via optional `onProgress?: (p: number) => void` prop).

- [ ] Failing tests: sets `--p` = 0.5 when scrolled halfway (mock rects); clamps to [0,1];
  disabled renders no sticky wrapper; `onProgress` called with clamped values.
- [ ] Implement → PASS. Checkpoint gate: full `pnpm test` for `src/components/landing` +
  `pnpm exec tsc --noEmit --incremental false` green. Inline code review of all primitives
  (hooks rules, cleanup, no per-request state, naming, docstrings English).

### Task A7: i18n — cosmos namespace (6 locales)

**Files:**
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — add `landing.cosmos.*`

**Interfaces:**
- Produces keys consumed by A4/A8/A9:
  `landing.cosmos.ghost.{act,know,anticipate,control,grow,connect,day,transparency,cta}`
  (ONE short uppercase-safe word each, meaningful per section, per locale — e.g. fr:
  act→AGIT, know→CONNAÎT, anticipate→REMARQUE, control→CONTRÔLE, grow→GRANDIT,
  connect→RELIE, day→JOURNÉE, transparency→PREUVES, cta→AVANCE; en: ACTS/KNOWS/NOTICES/
  CONTROL/GROWS/CONNECTS/A DAY→DAY/PROOF/AHEAD; de/es/it/zh equivalents, zh 2-3 ideograms),
  `landing.cosmos.planet.{maison,emails,agenda,memoire,voix,veille,skills,briefing}` (short
  labels), `landing.cosmos.preview_note` (footer note naming the preview), and
  `landing.cosmos.day_hint` (scroll hint under the pinned day title).
- [ ] Add keys to `en` first, then mirror to the 5 others (translated, not copied).
- [ ] Run the parity check exactly as the pre-commit hook does (`node scripts/check-i18n-parity.mjs`
  or the task the hook calls — read `.github/hooks/` to use the real command) → green.

### Task A8: Planetarium + count-up (hero ingredients)

**Files:**
- Create: `apps/web/src/components/landing/cosmic/Planetarium.tsx`
- Create: `apps/web/src/components/landing/cosmic/useCountUp.ts`
- Test: `apps/web/src/components/landing/cosmic/__tests__/planetarium.test.tsx`
- Test: `apps/web/src/components/landing/cosmic/__tests__/useCountUp.test.ts`

**Interfaces:**
- Produces: `<Planetarium />` (client): halo + 3 ellipse groups (`.cosmos-orbits` tilt
  wrapper) with 8 planets `{sizePx, colorToken, labelKey, orbit: 'out'|'mid'|'in', phaseS}`
  as a typed const `PLANETS` (exported for tests); labels via `useTranslation`; the whole
  component `aria-hidden` (decorative — the copy already names the domains).
  `useCountUp(target: number, opts: {decimals?: number; suffix?: string; durationMs?: number; locale: string})`
  → `{display: string; start: () => void}`; fr formatting via `toLocaleString(locale)`;
  reduced-motion or `durationMs: 0` → jumps to final on start.
- [ ] Failing tests: PLANETS has 8 entries across 3 orbits with 2–3 per orbit and ≥3
  distinct sizes; every labelKey exists in en translation.json (read file in test —
  imitate existing content-coverage guard style); useCountUp fake-timer run reaches exact
  final string `'99+'` / `'0,001 €'` (fr) and is monotonic; reduced-motion instant.
- [ ] Implement → PASS.

### Task A9: Cosmos page composition (`/[lng]/cosmos`)

**Files:**
- Create: `apps/web/src/app/[lng]/cosmos/page.tsx`
- Create: `apps/web/src/components/landing/cosmic/CosmosHero.tsx`
- Create: `apps/web/src/components/landing/cosmic/CosmosDay.tsx`
- Create: `apps/web/src/components/landing/cosmic/CosmosThemeDefault.tsx`
- Create: `apps/web/src/components/landing/cosmic/CosmosFinale.tsx`
- Test: `apps/web/src/app/[lng]/cosmos/__tests__/page.test.tsx`
- Test: `apps/web/src/components/landing/cosmic/__tests__/composition.test.tsx`

**Interfaces & composition contract:**
- `page.tsx` (server): `if (process.env.NODE_ENV === 'production') notFound();`
  metadata `{ robots: { index: false } }` + title; NO `AuthRedirect`, NO `TrackView`
  (preview must stay reachable logged-in and must not pollute ADR-178 funnel);
  wraps everything in `<div className="landing-page cosmos">` with `<CosmicBackdrop />`,
  `<CosmosThemeDefault />`, then reuses REAL sections in the REAL order:
  `LandingHeader`, `ChapterRail`, `CosmosHero` (cosmos variant of HeroSection),
  `EditorialChapters`, `BasicsBand`, `TransparencySection` (wrapped with
  `<GhostWord wordKey=".ghost.transparency" direction={1}>`), `UseCasesSection`,
  `CosmosDay` (pinned variant reusing `landing.day.*` + `Tabs`), `GallerySection`,
  `TechSection`, `ArchitectureDiagram`, `BlogPreviewSection`, `CosmosFinale` (cosmos skin
  around the real `landing.cta.*` content + planet horizon + dawn), `LandingFooter`.
  GhostWords for chapters are injected via a thin server wrapper around each
  `ChapterSection` anchor — implemented by rendering `<GhostWord>` siblings positioned by
  the chapter anchors' ids inside a `CosmosChapterGhosts` client component (maps
  `CHAPTERS[i].anchor → ghost key + alternating direction`, portals not needed: absolute
  divs appended inside each section via `document.getElementById(anchor).prepend`? NO DOM
  mutation — instead `EditorialChapters` gains an optional `ghosts?: boolean` prop
  rendering `<GhostWord>` as first child of each `ChapterSection` when true; default false
  keeps `/` byte-identical).
- `CosmosThemeDefault` (client): inline pre-paint script is impossible post-hydration —
  instead: `useEffect`: if `localStorage.getItem('theme') === null` → `setTheme('dark')`
  (next-themes); plus a `<Script id="cosmos-dark" strategy="beforeInteractive">` in
  `page.tsx` adding the `dark` class pre-paint when no stored theme (prevents FOUC).
- `CosmosHero` (server): reuses `landing.hero.*` keys, badges, `LANDING_STATS`,
  `InteractiveChatMockup`, GitHub/register links from `HeroSection` (copy the exact hrefs
  and key names from `HeroSection.tsx`), adds `.cosmos-rise` entrance delays, gradient
  accent span on the title's brand word, `<Planetarium />` behind the mockup, stats with
  `useCountUp` via a small client `TrustStat` subcomponent.
- `CosmosDay` (client): `PinnedScene heights={3.2}` + `Tabs` (existing component) with the
  4 profiles; each profile's 4 stops rendered as `.cosmos-glass` step cards on a
  horizontal `.cosmos-track` whose translateX is driven by `--p` (CSS calc consuming the
  measured max via a `--track-max` var set from a resize-measured ref); steps get
  `.lit`/`.focus` from `onProgress`; `disabled` fallback = the existing vertical `<ol>`
  markup pattern (same keys).
- `CosmosFinale` (server + tiny client dawn): real `landing.cta.*` copy and register link
  (copy exact keys from `CtaSection.tsx`), `.cosmos-globe` planet layers, `--dawn` set by
  a client `DawnDriver` using `useCosmosScroll` + `sectionProgress`.

- [ ] Failing composition test: renders `page` (with mocked i18n/server bits per existing
  page-test patterns — read `apps/web/src/app/[lng]/__tests__` or nearest page test for
  the harness) and asserts: all real section testids/headings present (hero heading, six
  chapter anchors `chapter-act`…`chapter-connect`, `#basics`, `#transparency`, `#day`,
  footer), NO `AuthRedirect` marker, ghost words present with `aria-hidden`.
- [ ] Failing unit tests: `CosmosDay` lights step k at `--p` ≥ k/4; disabled renders
  vertical list; `CosmosThemeDefault` calls setTheme('dark') only when storage empty.
- [ ] Implement all; `EditorialChapters` change is additive-only (`ghosts` prop default
  false) — assert `/` page snapshot-free byte-identity by grepping the diff of
  `EditorialChapters` usage in `app/[lng]/page.tsx` (must be none).
- [ ] Run full front gates: `task lint:frontend`; `pnpm exec tsc --noEmit --incremental false`;
  `pnpm test` (all); `pnpm test:coverage` thresholds green.
- [ ] Checkpoint: inline full code review (typing, a11y, hooks, i18n, CLAUDE.md react
  rules, no state on module singletons, English comments).

### Task A10: Docker dev runtime validation (Lot A)

- [ ] `docker restart lia-web-dev` (container never hot-reloads host edits — memory rule),
  wait for compile; `curl -sk` the route until 200 AND stylesheet link present
  (`grep -c 'rel="stylesheet"'` ≥ 1 — ADR-171 degraded-server trap).
- [ ] Chrome (devtools MCP): `http://localhost:3100/fr/cosmos` — verify dark-first
  (no stored theme → dark), hero planetarium, ghost drift, pinned day during scroll
  (measure sticky top during scroll — ADR-171 doctrine), finale dawn, light toggle,
  `/fr` unchanged; widths 1440 / 768 / 390 (no horizontal overflow:
  `scrollWidth − clientWidth === 0` at each width); reduced-motion emulation
  (`emulate` CPU/media) → static finals.
- [ ] Screenshots as evidence; fix-forward any defect found, re-run affected tests.
- [ ] **Documented deviation from spec §5**: hermetic Playwright specs cannot target the
  preview (they run against a production build where `/cosmos` is `notFound()`); the
  during-scroll sticky measurement, overflow and a11y sweeps are performed here via the
  browser MCP, and the Playwright specs land at swap time when `/` carries the identity.

### Task B1: Lot B — /more and /demo previews

**Files:**
- Create: `apps/web/src/app/[lng]/cosmos/more/page.tsx`
- Create: `apps/web/src/app/[lng]/cosmos/demo/page.tsx`
- Test: extend `apps/web/src/app/[lng]/cosmos/__tests__/page.test.tsx`

- [ ] Read `app/[lng]/more/page.tsx` and `app/[lng]/demo/page.tsx`; each cosmos preview
  re-renders the same content components inside `<div className="landing-page cosmos">` +
  `CosmicBackdrop` (+ dev gate + noindex + no telemetry), no content duplication (import
  the same section components the real pages use; if a real page inlines its content,
  extract it to a shared component in the SAME file structure the page already uses —
  additive, real route untouched).
- [ ] Add skin rules to the cosmos CSS block only if a surface renders unreadably (review
  in browser); tests: both preview pages render their real content headings; gates green.

### Task C1: Lot C — calm reading variant

**Files:**
- Modify: `apps/web/src/styles/globals.css` (append `.cosmos-calm` sub-scope)
- Create: `apps/web/src/app/[lng]/cosmos/lecture/page.tsx` (dev-only preview hosting the
  real Story page content in the calm scope)
- Test: extend cosmos page tests

- [ ] `.cosmos-calm`: same backdrop tokens, glows ≤ half opacity, no ghost words, no
  choreography classes, card surfaces near-opaque for contrast (AA verified in browser).
- [ ] Preview page renders the real story content (import the story page's content
  component; if inlined, wrap via an extracted shared component — additive only).
- [ ] Browser contrast check both themes; gates green.

### Task F1: Ratchets, docs, final review

- [ ] `pnpm a11y:ratchet && pnpm react-hooks:ratchet && pnpm cc:ratchet` — improve-only;
  if measured debt decreased, run `task ratchet:update` to LOWER caps (never raise).
- [ ] `task test:frontend:coverage` — if new floors are comfortably exceeded, raise
  per-file thresholds keeping ≥2 pts margin (memory rule).
- [ ] Update docs: `docs/INDEX.md` entry for the spec; note in spec that plan executed.
- [ ] Full `task ci:fast`-equivalent front gates; final inline review sweep; report to
  owner with evidence (URLs :3100, screenshots, test counts) — swap decision is theirs.

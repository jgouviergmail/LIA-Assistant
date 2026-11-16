# Landing positioning and comparison Implementation Plan

> **For agentic workers:** executed inline (owner rule: no subagents) with superpowers:executing-plans. No git
> step: the owner handles git.

**Goal:** Hero without the brick constellation → positioning → video → five argument tiles → comparison table →
gallery, in six languages, plain words, every claim true.

**Architecture:** language-neutral data (`comparison-data.ts`) + locale keys; two server sections resolve the
living map's brick names server-side (`bricks.ts`); one client explorer owns the view and reading filters.

**Tech Stack:** Next.js 16 server/client components, react-i18next, Tailwind, Lucide (`@/lib/icons`), vitest,
Playwright.

**Spec:** `docs/superpowers/specs/2026-11-15-landing-positioning-comparison-design.md`

## Global Constraints

- Six locales (fr, en, de, es, it, zh), `tu` everywhere (`du`, `tú`, `tu`, `你`); plain words for non-experts.
- "60+ bricks" is rendered from `{{count}}+`, `count` = the living map's brick count floored to ten.
- Competitor cells state only what the competitor's official pages (or reporting on Meta's announcements) say,
  read on 2026-11-15; humour kept, no falsehood, no unverifiable superlative ("first", "only").
- Landing charter: cosmos skin, theme colour, Lucide icons; no emoji in chrome; no version number.
- `/maps` keeps its constellation (`FunctionalMap`); only the home page loses `LandingConstellation`.

## Review Focus

- A duel filter that leaves a stale column or a stale contender card → columns and cards follow the view.
- A narrow phone (320 px) with the four contenders → stacked cards, no horizontal page scroll.
- A brick id renamed in the living map → the data contract test fails before a dead link ships.
- A locale missing one cell string → the contract test names the key and the locale.
- The reading mode hiding the only text of a cell → the head line always stays.

---

### Task 1: Data, brick resolution and locale content

**Files:** Create `apps/web/src/components/landing/comparison/comparison-data.ts`,
`apps/web/src/components/landing/comparison/bricks.ts`,
`apps/web/src/components/landing/comparison/__tests__/comparison-data.test.ts`; modify the six
`apps/web/locales/*/translation.json` (new `landing.positioning`, `landing.arguments`, `landing.comparison`).

**Interfaces (produces):** `ContenderId`, `CompetitorId`, `ComparisonStatus`, `CriterionId`, `ArgumentId`,
`CONTENDER_IDS`, `COMPETITOR_IDS`, `CONTENDER_NAMES`, `BULLETS_PER_CONTENDER`, `CRITERIA: readonly Criterion[]`
(`{ id, bricks, status: Record<ContenderId, ComparisonStatus> }`), `ARGUMENT_IDS`, `COMPARISON_SOURCES`,
`COMPARISON_SOURCES_READ_ON = '2026-11-15'`, `comparisonLocaleKeys(): string[]`;
`brickCountFloor(): number`, `comparisonBricks(lng): Record<CriterionId, ComparisonBrickLink[]>`.

- [ ] Test: every `CRITERIA[*].bricks` id exists in `functional.json`; `comparisonLocaleKeys()` all resolve to a
  non-empty string in the six locales; `brickCountFloor()` is a multiple of ten ≤ the brick count; every locale's
  `thesis_body` carries `{{count}}+` and no hard-coded digit.
- [ ] Run, see it fail; write data, resolver and the six locales (scripted, byte-safe); run, see it pass.

### Task 2: `ComparisonExplorer` (client)

**Files:** Create `apps/web/src/components/landing/comparison/ComparisonExplorer.tsx` and its test.

**Interfaces:** consumes Task 1; props `{ lng: Language; bricks: Record<CriterionId, ComparisonBrickLink[]> }`.

- [ ] Tests (fr and en, real resources): four column headers by default; « Face à Hermes » leaves LIA and Hermes
  only, `aria-pressed` follows; « Les punchlines » hides bullets, « Les faits » hides punchlines, the head stays;
  each status reads its word; brick links go to `/maps/functional#f.planning` (fr) and `/en/...` (en); the sources
  line formats 2026-11-15 in the page's language.
- [ ] Implement: two `role="group"` button bars, contender cards, a `<table>` from `lg`, stacked cards below.

### Task 3: Sections, hero and page

**Files:** Create `editorial/PositioningSection.tsx`, `editorial/ArgumentsSection.tsx`,
`comparison/ComparisonSection.tsx` and a section test; modify `cosmic/CosmosHero.tsx`, its test,
`app/[lng]/page.tsx`, `styles/maps.css`; delete `cosmic/LandingConstellation.tsx` and its test.

- [ ] Tests: hero renders no constellation and its scroll hint targets `#positioning`; positioning renders its
  title, both paragraphs and the thesis with the floored count; arguments render five titled tiles in order.
- [ ] Implement and wire: hero → positioning → video → arguments → comparison → gallery.

### Task 4: Browser guard and documentation

**Files:** modify `apps/web/e2e/smoke/landing-mobile-overflow.spec.ts`, `docs/technical/LANDING_PAGE.md`.

- [ ] Replace the home-page constellation journey with the comparison's (duel, reading modes) at 375 and 320 px.
- [ ] Document the new sections, guards and namespaces; fix the hero description.

### Task 5: Verification

- [ ] `task lint:frontend`, `pnpm exec tsc --noEmit --incremental false`, targeted vitest, `task test:frontend`,
  `task lint:i18n`, `task lint:docs`; the overflow spec; the page in the dev container, light and dark, desktop
  and phone widths.

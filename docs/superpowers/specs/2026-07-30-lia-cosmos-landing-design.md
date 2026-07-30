# LIA Cosmos — Public-space visual identity (design spec)

**Date**: 2026-07-30 · **Status**: validated by owner (mockup v4 approved) · **Scope**: apps/web public pages

## 1. Context and goal

The owner wants the public space restyled with a scroll-driven "cosmic" identity inspired by
https://www.lialive.ai (a third-party product coincidentally named LIA), **without copying it**.
A scrollable mockup (4 iterations, validated 2026-07-30) fixed the visual language. This spec
translates the validated mockup into an implementation contract for the real site.

**Owner-signed decisions** (AskUserQuestion arbitrations, 2026-07-29):

| Decision | Choice |
| --- | --- |
| Ambition | Restyle + targeted scroll choreographies (not a full narrative rebuild) |
| Theme | Landing dark-first; toggle stays; polished sober light variant |
| Page scope | Whole public space, in lots (A landing, B /more + /demo, C reading pages) |
| Palette | LIA palette intensified: blue `#4F8DFD` → violet `#8B5CF6` → cyan `#38D4F5` on near-black `#06070F` |
| Technique | In-house native primitives (no animation library, no new dependency) |
| Validation | Parallel route on docker dev — owner compares current vs revised, then swap |

**Non-negotiable owner requirements**: all existing landing content is reused verbatim
(same i18n keys, same catalogs — the coverage guard `editorial-content-coverage.test.ts`
must keep passing); ghost words slightly larger than mockup; every animation must *demonstrate
a product idea* (doctrine: "one animation = one product idea", never motion for motion's sake);
maximum tests; polished responsive; ratchets updated after improvements.

## 2. Identity system

### 2.1 Tokens (globals.css, scoped)

All cosmos styling lives under a `.cosmos` scope class (set on the page wrapper), so the
existing landing is untouched until the final swap. Tokens are CSS custom properties defined
on `.cosmos` (dark values — the identity's default), overridden under `html:not(.dark) .cosmos`
for the sober light variant (the toggle keeps driving the existing `dark` class on `<html>`):

- Grounds: `--cosmos-bg #06070F`, `--cosmos-bg-2 #0A0E1D` (light: `#F5F6FC` / `#ECEEF9`)
- Signature gradient `--cosmos-grad`: 100deg blue → violet 55% → cyan
- Glows: blue/violet/cyan rgba levels as in mockup; `--cosmos-line`, `--cosmos-glass`
- Ghost text: transparent fill + `-webkit-text-stroke` (dark `rgba(148,163,220,.30)`,
  light `rgba(27,33,64,.14)`), size `clamp(7rem, 28vw, 26rem)` (owner: "a bit larger")

### 2.2 Fixed cosmic layers

One fixed backdrop for the whole page (component `CosmicBackdrop`): near-black ground,
3 radial nebulas + 2 slowly drifting aurora blobs (transform-only), star canvas (drawn once,
static, ≤180 stars, hidden in light), film grain (SVG turbulence data-URI, opacity .05/.03).
Sections become transparent — the scroll traverses one continuous cosmos.
`ConstellationBackground` (currently a dead export) is either rewired inside `CosmicBackdrop`
or deleted in the same change (CLAUDE.md: wire it or remove it).

### 2.3 Primitives (apps/web/src/components/landing/cosmic/)

| Primitive | Behavior | A11y/perf contract |
| --- | --- | --- |
| `CosmicBackdrop` | fixed layers above | `aria-hidden`, zero continuous JS |
| `GhostWord` | giant outlined word behind a section, translated (i18n key), lateral drift driven by scroll progress, direction prop alternates per section | `aria-hidden`, `overflow: clip` on host section, transform-only, no drift under reduced-motion |
| `GlowCard` | glass card (translucent bg, 1px line, colored shadow), optional tilt | pure CSS |
| `PinnedScene` | tall section (n×100vh) + sticky 100vh stage; exposes scroll progress as `--p` CSS var via one rAF scroll listener | mobile (<760px) and reduced-motion fall back to static flow; sticky works since ADR-171 (`body{overflow-x:clip}`) |
| `BlurReveal` | blur→sharp reveal on IntersectionObserver (same pattern as existing `ScrollStage`) | reduced-motion → final state instantly |
| `useCosmosScroll` | single shared rAF scroll loop feeding ghost drift, pinned progress, dawn | passive listener, cleanup on unmount |

The existing `ScrollStage` / `FadeInOnScroll` remain and are reused as-is inside the cosmos skin.

### 2.4 Dark-first mechanism

The cosmos preview route (and, at swap time, the public layout) renders dark by default when
the visitor has no stored theme preference: a small inline anti-FOUC script (same pattern as
next-themes) applies `dark` when `localStorage.theme` is absent, **scoped to public pages**.
An explicit user choice (toggle) always wins, everywhere. Consequence accepted by owner: a
first-time visitor who enters via the landing stays dark in the app until they toggle.

## 3. The landing, section by section (Lot A)

Parallel route **`/[lng]/cosmos`** (dev-only: `notFound()` in production) renders the full
real landing content in the cosmos skin. Existing sections and i18n keys are reused; only the
skin and choreography wrappers are new. Comparison: `:3100/fr` vs `:3100/fr/cosmos`.

| Real section (reused) | Cosmos treatment | Meaningful animation |
| --- | --- | --- |
| `HeroSection` (copy, badges, stats, `InteractiveChatMockup`) | orchestrated entrance (badges → title lines → copy → CTA → stats), gradient on the title accent | **Planetarium**: 8 feature-planets (sizes 10–26px) on 3 tilted ellipses (2-3 per ellipse, phase-shifted, luminous trails, upright labels): Maison, Emails, Agenda / Mémoire, Voix & appels, Veille / Skills, Briefing. Chat mockup stays the centerpiece. Stats count up. |
| `EditorialChapters` (6 chapters, moods, bubbles, catalogs) | each chapter gets a translated `GhostWord` (alternating drift), vignettes/scenes hosted in `GlowCard` framing | existing per-chapter vignettes/scenes stay authoritative (they already choreograph via ScrollStage); the cosmos skin restyles their frame only — content and animations unchanged |
| `BasicsBand` | calm glass band, chips as pills | none (calm by design) |
| `TransparencySection` (cost motif, 4 proofs, mid CTA) | `GhostWord` PREUVES; proofs in `BlurReveal` cascade | cost figure and numbers **count up** on arrival |
| `UseCasesSection` | GlowCards | card flip/reveal on hover (outcome) |
| `DayTimeline` (4 profiles × 4 stops, Tabs) | **PinnedScene**: on desktop the active profile's day becomes the horizontal scroll-driven timeline (steps light up, depth arc, progress bar); Tabs remain the profile switcher | the day advances with the visitor's scroll |
| `GallerySection` | GlowCards + subtle 3D tilt on hover | screenshots as portals |
| `TechSection` + `ArchitectureDiagram` | calm variant, ghost word SOUS LE CAPOT (short: CAPOT/TECH per locale review) | data-flow pulse along diagram edges (existing SVG) if cheap, else static |
| `BlogPreviewSection` | GlowCards | none |
| `CtaSection` | **cosmic finale**: smooth planet horizon (deep sphere, drifting clouds, crisp cyan→white→violet atmosphere rim + bloom), scroll-driven dawn (`--dawn`), moonlet transit, `GhostWord` from the CTA title's key word | the dawn rises as you arrive |
| `LandingHeader` / `LandingFooter` / `ChapterRail` | glassy blur header on scroll; neon rail with luminous active state; footer fused into cosmos | — |

**Ghost words are translated** (new i18n namespace `landing.cosmos.ghost.*`, 6 locales, one
short word per section chosen per locale — zh gets `_one` duplicates where pluralized).
They must carry the section's meaning (owner: "COSMOS made no sense" → per-section words).

## 4. Lots B and C

- **Lot B** — `/more` and `/demo` adopt the cosmos skin via the same scope class + primitives.
  Preview: dev-only parallel routes (`/[lng]/cosmos/more`, `/[lng]/cosmos/demo`) reusing the
  existing scene components unchanged.
- **Lot C** — reading pages (story, philosophie, technique, blog, FAQ, guides): **calm
  variant** only — cosmos backdrop attenuated, sober cards, no choreography, reinforced
  reading contrast. Shipped as scoped styles; applied at swap time. Preview: one representative
  dev-only route to validate the calm treatment.

## 5. Quality contract

- **Perf**: animations use `transform`/`opacity` only; no continuously-animated blur; one
  shared rAF scroll loop; star canvas drawn once; prod serves from an RPi5.
- **A11y**: axe contrast AA on both themes; all decorative layers `aria-hidden`; keyboard and
  focus-visible preserved (header, rail, tabs, catalogs); reduced-motion = final state, zero
  motion (durations *and delays* zeroed).
- **No regression**: the current landing route is byte-identical until swap; the coverage
  guard test keeps passing; the overflow e2e guard stays green (ghosts clipped).
- **Tests**: unit tests for every primitive (staging, reduced-motion, drift math, pinned
  progress clamping, count-up formatting fr locale); component tests for the cosmos page
  composition (all real sections present); i18n parity for new keys (6 locales).
  E2e (hermetic): pinned scene measured **during** scroll (ADR-171 guard doctrine), overflow,
  a11y sweep on `/cosmos`.
- **Gates**: `task lint:frontend`, non-incremental `tsc`, `task test:frontend:coverage`,
  ratchets (a11y/react-hooks/cc) — raise floors after improvement, never lower.
- **Runtime validation**: docker dev (`lia-web-dev`, :3100) with `docker restart` before any
  browser verdict; owner compares `/fr` vs `/fr/cosmos`.

## 6. Swap plan (after owner validation)

> **Executed 2026-07-30** (owner validation received): `/` carries the cosmos
> composition with AuthRedirect/TrackView/JsonLd restored; `/more` and `/demo`
> carry the full scope; story/why/how/faq/blog(+articles)/privacy/terms carry
> the calm scope; every `/cosmos` preview route, `CosmosPreviewNav`,
> `CalmPreview`, `HeroSection`, `CtaSection` and the unused landing barrel are
> deleted; hermetic Playwright specs added (pinned-day measured during scroll,
> axe AA on `/` both themes) — all green. Release/deploy still pending owner
> instruction.

1. The `/` page adopts the cosmos composition (scope class on the landing wrapper).
2. The `/cosmos` preview routes are deleted (no dead code).
3. Obsolete styles of the old skin are purged in the same change.
4. Lot C calm styles activate on reading pages.
5. Release + deploy on owner's explicit instruction only.

## 7. Risks and mitigations

- **Sticky regressions** → follow ADR-171: never reintroduce a scrollport ancestor; e2e
  measures position during scroll.
- **Mobile perf** → planetarium reduced (smaller orbits, labels hidden), pinned scene falls
  back to vertical flow, star count capped by width.
- **Bundle** → zero new dependency; primitives are small client components; heavy nothing.
- **SEO** → preview routes are dev-only (`notFound()` in prod); at swap, no URL changes.
- **i18n drift** → strict parity enforced by the pre-commit hook; ghost words reviewed per
  locale (short, meaningful, uppercase-safe).

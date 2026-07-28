# "Encore +" Public Page (`/more`) — Verified Design

**Date:** 2026-07-28 · **Status:** IMPLEMENTED AND VERIFIED 2026-07-28 (uncommitted) — all
gates green: 120 unit tests (guards + hook + 26-scene matrix + MoreCard/MoreContent), full
`task lint` (ratchets included), frontend coverage suite (67.43 % stmts — floors kept per the
vitest.config doctrine, lines 67.95 < 68), e2e axe 6/6 (light+dark, animating+paused),
overflow 375/320 px + 6-locale sweep, production-bundle runtime proof (BUILD_ID-verified)
with light/dark/mobile captures. Plan: `docs/superpowers/plans/2026-07-28-more-page.md`.
**Baseline:** HEAD `3df0c945` (v1.25.33), clean working tree.

## Purpose

A sixth public page, linked in the landing header after FAQ, that showcases the **small UX/UI
attentions** — micro-features that are real product value and differentiation but too small to
appear among the 36 major feature cards of the editorial landing
(`apps/web/src/components/landing/editorial/chapters-data.ts`, anti-regression contract
`REQUIRED_FEATURE_KEYS`). The page presents *craft*, one level below *capabilities*, and must
not duplicate any major card.

## Signed-off decisions (user, 2026-07-28)

| Decision | Choice |
|---|---|
| Concept | **C — "Les moments"**: 5-6 sections by usage moment, every card animated |
| URL segment | **`/more`** (nav label localized: fr "Encore +", en "More", …) |
| Scope | Curation **26 cards** in 6 sections |
| Illustration | **All animated** — every card carries its own micro-animation |
| Amendment 1 | fr copy says "cliquables", not "tapables" (follow-up chips card) |
| Amendment 2 | Voice/number card dropped (reads as a bug fix); replaced by `cost_transparency` |

## Editorial rules (binding)

- **No version numbers anywhere on the page** — showcase, not changelog (only
  CHANGELOG/ADR/FAQ.changelog are historical surfaces).
- Every claim on the page must be true of the current product; the evidence table below pins
  each card to code. A card whose surface disappears must be removed from the page in the same
  change (docstring-vs-behavior rule applied to marketing copy).
- Copy is written natively per language (no truncated locales), fr uses the typographic
  apostrophe U+2019, tone matches the existing landing (warm, concrete, first-person product).
- **No numeric claims in card copy** unless the number comes from a constant re-measured
  every release (`LANDING_STATS` protocol). Point-in-time measurements are unmanaged drift
  surfaces: the quota threshold is settings-driven (never hard-code a threshold) and the
  settings-search keyword count moves with every keyword added. Those two cards use
  qualitative copy ("warned well before the wall", "understands your language"). The hero
  counter is exempt because it is derived from `MORE_SECTIONS` at render.

## Content — 26 cards, 6 moments

Sections are numbered 01-06 with alternating tinted backgrounds (rhythm of
`ChapterSection`). Card keys below are the i18n/data keys.

### 01 · Quand vous écrivez (4)

| Key | Claim | Evidence |
|---|---|---|
| `draft_survives` | Typed text survives refresh/navigation; ↑ recalls the last sent message | `src/hooks/useInputDraft.ts` (UXR Lot 2/A7) |
| `slash_commands` | `/` opens a filtered, keyboard-navigable command menu | `src/components/chat/SlashCommandMenu.tsx`, `src/lib/slash-commands.ts` |
| `paste_screenshot` | Pasting a screenshot into the composer attaches it | `src/components/chat/ChatInput.tsx` (onPaste/clipboardData; v1.25.33) |
| `drop_zone` | Real drag-and-drop target for files | `src/components/chat/ChatInput.tsx` (onDrop/DragEvent; v1.25.33) |

### 02 · Quand LIA répond (5)

| Key | Claim | Evidence |
|---|---|---|
| `followup_chips` | 0-3 clickable follow-up suggestions under the latest response | `src/components/chat/FollowupChips.tsx` (UXR Lot 4/A2) |
| `scroll_return` | Floating scroll-to-bottom button with a "new response" badge | `src/components/chat/ScrollToBottomButton.tsx` (UXR Lot 3/A3) |
| `bubble_actions` | Copy · 👍 · 👎 row under every bubble | `src/components/chat/ChatMessage.tsx` action row (PERSO lot, v1.25.16) |
| `share_export` | Share or export a response | `src/components/chat/ShareResponseMenu.tsx` (v1.25.33) |
| `backstage` | See what LIA actually did (execution trace disclosure) | `src/components/chat/ExecutionTraceDisclosure.tsx` (ADR-133 V2) |

### 03 · Quand ça se passe mal (5)

| Key | Claim | Evidence |
|---|---|---|
| `actionable_errors` | The real server cause reaches the user, not a generic apology | `src/lib/api-error.ts` `readErrorDetail`, threaded through `api-client.ts:295` (ADR-152, 21 sites) |
| `retry_turn` | Replay a failed turn in one click | behavioral proof `src/components/chat/__tests__/retry-affordance.test.tsx` (v1.25.24); pin the rendering component during implementation |
| `quota_warning` | Warned well before the quota wall (threshold is settings-driven — copy stays qualitative) | `src/components/usage/UsageWarningBanner.tsx` (v1.25.24) |
| `image_expiry` | Generated images announce their expiry | `ImageExpiryNotice`, `src/components/chat/ChatMessage.tsx:283` + `src/lib/image-expiry.ts` |
| `attachment_limits` | A rejected attachment names the limit that applies | `src/components/chat/ChatInput.tsx:520` (per-type caps; v1.25.33) |

### 04 · Quand vous cherchez (4)

| Key | Claim | Evidence |
|---|---|---|
| `settings_search` | Settings search understands everyday words, **in your language** (keyword count stays out of copy — it moves every release) | `src/components/settings/SettingsSearch.tsx` (ADR-172) |
| `deep_links` | Every settings section has an address (30 deep-linkable sections) | ADR-172 / v1.25.32 deep-link table |
| `history_search` | Full conversation-history search | `src/components/chat/search/` (QW-2, v1.25.12) |
| `mobile_logo_nav` | On the phone, the logo becomes the navigation | `src/components/dashboard/MobileNavMenu.tsx` (v1.25.24) |

### 05 · Au quotidien (4)

| Key | Claim | Evidence |
|---|---|---|
| `briefing_custom` | Morning briefing: your cards, your order | `src/components/settings/BriefingGridSettings.tsx` (UXR Lot 5/B4) + "Personnaliser" entry (v1.25.33) |
| `starter_checklist` | Getting-started checklist with an end-of-onboarding micro-celebration | `src/components/dashboard/StarterChecklistCard.tsx` (UXR Lot 6/A10 + v1.25.33) |
| `empty_starters` | Three starter prompts on an empty chat | `src/components/chat/__tests__/ChatMessageList.starters.test.tsx` (v1.25.24) |
| `pwa` | Installable (PWA), system share target, offline | UXR Lot 9/A6 (`app/[lng]/share/page.tsx`) + v1.25.17 offline PWA |

### 06 · Invisibles mais senties (4)

| Key | Claim | Evidence |
|---|---|---|
| `background_response` | Leave the page — the response keeps running and catches up with you | ADR-117 background runs + ADR-134 reconnect banner |
| `widgets_travel` | Widgets travel with their message (reload, other device) | ADR-137 (v1.25.11) |
| `cost_transparency` | See what each response consumed (tokens/cost, opt-in display) | `src/components/tokens-display-toggle.tsx`, `ContextUsagePill`, `tokens_display_enabled` in `ChatMessage.tsx` |
| `a11y_care` | Reduced-motion honored, AA contrast, everything keyboard-reachable | `e2e/a11y/` axe gates; prefers-reduced-motion handling (v1.25.32) |

## Page structure

`LandingHeader` → hero → sections 01-06 → "craft in numbers" band → CTA → `PublicFooter`.

- **Hero**: title + subtitle + `AnimatedCounter` ("26 petites attentions sur cette page — et
  d'autres à chaque version"). The count is derived from `MORE_SECTIONS` at render, never
  hard-coded.
- **Sections**: numbered header (01-06 + moment title + one intro line), card grid
  1 → 2 → 3 columns (mobile → md → lg), `FadeInOnScroll` entrances, alternating
  `tinted` backgrounds.
- **Card anatomy**: animated stage on top (fixed height to prevent CLS), lucide icon + title,
  one-sentence description. The stage is decorative (`aria-hidden`); title + description carry
  the meaning (validated hero-mockup pattern).
- **Craft band**: reuses `LANDING_STATS` (tests, uiLanguages, releases) — no new numbers, no
  version strings.
- **CTA block**: same pattern as the FAQ page (`landing.cta.*` keys, register link).

## Files (all < 600 logical SLOC)

| File | Role |
|---|---|
| `app/[lng]/more/page.tsx` | Server component: `generateMetadata` (canonical + 6-locale alternates + OG/Twitter), `BreadcrumbJsonLd`, layout — exact `/faq` page pattern |
| `components/landing/more/MoreContent.tsx` | Client: sections layout, grid, hero counter |
| `components/landing/more/more-data.ts` | Source of truth: `MORE_SECTIONS` (section keys, card keys, icon map, scene map). Completeness guard test in the `chapters-data` style |
| `components/landing/more/primitives.tsx` | Shared mini-UI vocabulary: MiniComposer, MiniBubble, MiniToast, MiniSettingRow, Cursor, KeyCap — theme tokens only (dark-mode native) |
| `components/landing/more/useLoopedTimeline.ts` | Timeline hook (contract below) |
| `components/landing/more/scenes-write.tsx` … `scenes-unseen.tsx` | 6 files, ~4-5 scene components each |
| `components/landing/more/__tests__/` | Guard + hook + scene smoke tests |

If a scenes file approaches the SLOC cap, split by scene — never bump the cap.

## Animation system contract

- `useLoopedTimeline(steps, { active })`: declarative steps (`{ at: ms, apply: state }`),
  driven **exclusively by timers** (`setTimeout`) — never `animationend`/`transitionend`
  (jsdom/React 19 never delivers them; hard-won 2026-07-28). Loops with a rest pause between
  cycles. All timers cleared on unmount and when `active` drops.
- **In-view gating**: scenes animate only while intersecting the viewport
  (IntersectionObserver), one observer per card via a small shared hook.
- **Reduced motion**: when `matchMedia('(prefers-reduced-motion: reduce)')` matches, the hook
  returns the **final step's state immediately** and never schedules a timer — every scene
  therefore defines a meaningful resting frame. Same pattern as `AnimatedCounter.tsx:34-35`.
- **Dark mode**: primitives use semantic tokens (`bg-background`, `text-muted-foreground`,
  `border-border`, `bg-primary/10`…) exclusively; no hard-coded colors.
- **Global pause control (WCAG 2.2.2 Pause, Stop, Hide)**: the looping scenes auto-start and
  collectively last more than 5 s, so `prefers-reduced-motion` alone is NOT sufficient — the
  page carries a visible pause/play toggle (`AnimationPauseToggle`, native `button`,
  `aria-pressed`, visible focus, translated label). A `MoreAnimationContext` exposes
  `playing`; `useLoopedTimeline` animates only when `playing && inView && !reducedMotion`.
  Session-local state, no persistence. Side benefit: the axe e2e can pause animations to
  stabilize scans.
- **No new dependencies.** CSS transitions/keyframes + staged class toggles only.
- **CLS**: every stage has a fixed height per breakpoint.
- **Bundle**: scenes are plain light components (no heavy libs), statically imported by their
  section — no `next/dynamic` needed unless measured otherwise.

## i18n (~70 keys × 6 locales)

- `landing.nav.more` (header) and `public_footer.more` (footer).
- New top-level namespace `more.*`: `meta.{title,description}`, `hero.{title,subtitle,counter}`,
  `sections.s1..s6.{title,intro}`, `cards.<key>.{title,desc}` (26 × 2), `craft.*`, and
  `controls.pause_animations` (the WCAG 2.2.2 toggle label).
- Strict key parity across en/fr/de/es/it/zh (pre-commit hook); no pluralization expected —
  if any `_one/_other` appears, duplicate the value for zh.
- fr uses U+2019; all copies natively written (translation-truncation trap, measured
  2026-07-26).

## Mandatory integration points (evidence-pinned)

1. `LandingHeader.tsx` `PAGE_LINKS` (line ~23): add `{ id: 'more', key: 'landing.nav.more', href: '/more' }` after `faq` — serves desktop **and** mobile menus.
2. `src/lib/api-client.ts` `PUBLIC_ROUTE_SEGMENTS` (line ~155): add `'more'` — the
   filesystem-scanning completeness test fails the build otherwise.
3. `src/app/sitemap.ts`: `{ path: '/more', changeFrequency: 'monthly', priority: 0.7 }`.
4. `src/components/layout/PublicFooter.tsx` **and**
   `src/components/landing/LandingFooter.tsx`: page link + `public_footer.more` key.
5. `e2e/a11y/axe-public-pages.spec.ts`: `/more` scans, light **and** dark, animations enabled,
   AC-002 policy (every critical/serious violation blocks).
6. Mobile overflow guard for `/more`: new `e2e/smoke/more-overflow.spec.ts` reusing the
   exported `overflowReport` helper from `landing-mobile-overflow.spec.ts` (extract it to a
   shared module) — static pass at 375 px and 320 px (WCAG 1.4.10) plus one pass with scene
   timelines running (the hero-oscillation lesson: overflow can exist only mid-animation).
7. `public/llms.txt`: one line referencing the page in the site map area.

## Tests

- **Data guard**: every `MORE_SECTIONS` card key has an icon, a scene, and `more.cards.<key>.*`
  keys in `en` + `fr` resources (parity hook covers the other four); card count on the page ==
  count announced by the hero counter.
- **Hook**: fake-timer tests — step application order, loop + rest, `active` gating,
  reduced-motion short-circuit, full timer cleanup on unmount.
- **Pause control**: toggling stops timer advancement for every mounted scene and resumes it;
  `aria-pressed` reflects state; label translated; keyboard-activatable.
- **Scenes**: smoke — each of the 26 scenes mounts, advances through a full cycle under fake
  timers without errors, and renders its resting frame under mocked reduced-motion.
- **Page**: heading hierarchy (single h1, sections as h2), stages `aria-hidden`, nav/footer
  links present.
- **Gates**: `task lint` (a11y/hooks/cc ratchets + non-incremental tsc), `task
  test:frontend:coverage` (per-file thresholds), i18n parity, targeted e2e (axe + overflow),
  browser validation through the `lia-web-dev` container (with `docker restart` — no host hot
  reload).

## Non-goals

- No backend change, no new dependency, no new metric.
- No duplication of the 36 major feature cards (`REQUIRED_FEATURE_KEYS`) — the guard test for
  this page checks its card keys are disjoint from that inventory.
- No screenshots/videos — everything is drawn with theme tokens (weightless, dark-native,
  i18n-safe).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| 26 animated cards → jank on low-end mobile | In-view gating; CSS-only transforms/opacity; rest pauses; no JS-driven per-frame work |
| Ratchet regressions (a11y/hooks/cc) on 10+ new files | Simple per-scene components; shared hook; ratchets run in `task lint` before any completion claim |
| Copy drift vs product truth | Evidence table above — every card carries a `file:line` or ADR anchor; re-verify at implementation before writing copy |
| i18n volume (~420 strings) | Written natively per language in one pass; parity hook blocks omissions |

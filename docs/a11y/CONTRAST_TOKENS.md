# Design-System Contrast Architecture (AC-002)

How LIA's theme tokens guarantee WCAG 2.x AA contrast across the 5 themes ×
light/dark/OLED — and how that guarantee is enforced so it cannot silently
regress.

## The contract

Every text-bearing token pairing the UI actually produces meets **4.5:1**
(normal text, WCAG 1.4.3); the focus ring meets **3:1** against the page
background (WCAG 1.4.11). "Actually produces" includes the states a static
scan never sees:

- solid buttons **and** their `/90` hover over the lightest underlay (card);
- the signature soft pattern `bg-<accent>/15 text-<accent>` (dashboard nav,
  soft buttons, badges) **and** the alert/toast tints up to `/20`;
- muted text on every neutral surface, including the `muted` tint itself.

## Token architecture (the two patterns)

Accents (`primary`, `destructive`, `success`, `warning`) follow one symmetric
rule per mode:

| Mode | Accent | `*-foreground` (text on solid accent) | Soft/tint text |
|---|---|---|---|
| Light | **dark enough to be text** on `background` and on its own `/15..20` tint | near-white (`98%`) | `text-<accent>` |
| Dark | **bright enough to be text** on the dark surfaces | near-black (`18%`) | `text-<accent>` |

Two consequences, both deliberate:

1. **One accent token serves both roles** (surface and text). That is what
   forces light accents down to L≈42–50 % and dark `destructive` up to 71.5 %.
2. **Soft variants color their text with the accent itself**, never with
   `*-foreground` (a `*-foreground` tuned for the solid surface is illegible
   on the tint in the opposite mode — the pre-fix softWarning was 1.24:1 in
   dark mode).

## The third depth: OLED

`html.dark[data-oled]` is a **refinement** of dark, not a sixth theme
(ADR-243). It overrides six neutral surfaces and nothing else, so every accent
keeps the dark values the table above describes, and `border` / `input`
deliberately inherit them: measured, `oklch(32%)` reads better against absolute
black (1.66) than against the dark ground (1.48).

Surfaces are calibrated against the **shipped dark mode**, never against zero,
so nothing separates less than it already did:

| pair | dark | OLED |
|---|---|---|
| card vs background | 1.09 | 1.10 |
| border vs background | 1.48 | 1.66 |
| border vs card | 1.37 | 1.51 |

Two cascade facts constrain where those overrides may live, and both are
load-bearing:

- The selector must be `html.dark[data-oled]`, scoring (0,2,1). A bare `.oled`
  class scores (0,1,0) and loses to `[data-theme='x'].dark` (0,2,0) — silently,
  and only for users who picked an accent.
- `lia-components.css` is `@import`ed **without `layer()`**, so its `.dark`
  block is unlayered and beats `@layer theme` at any specificity. The V3
  display layer's OLED overrides therefore live in that file, next to the
  values they replace.

Requiring `.dark` in the selector is also what makes light mode immune with no
application-side guard at all.

## Forbidden patterns

- **Alpha-diluted text tokens**: the composite drops below AA by
  construction past a per-token threshold (both modes verified):
  `text-muted-foreground/<100` — always forbidden (use the plain token);
  `text-foreground/<80` — forbidden (4.26 at /70 in light);
  `text-primary/<90` — forbidden (3.89 at /80 in light, 4.45 in dark).
  `text-foreground/80+` (5.57) and `text-primary/90` (4.70) remain allowed,
  including as hover states.
- **Third-party palettes on text** (e.g. sonner `richColors`): toast colors
  come from the per-type classNames using theme tokens.
- Darkening a soft tint on hover (`hover:bg-<accent>/25`) — hover feedback on
  soft variants is border + shadow, the tint stays `/15`.

## Enforcement (three layers)

1. **Unit guard** — `apps/web/src/styles/__tests__/design-contrast.guard.test.ts`
   parses `globals.css`, converts OKLCH→sRGB, and asserts the full pair matrix
   for all 15 palettes, including hover blends and self-tints. Any palette
   edit below AA fails `pnpm test` before a browser ever renders it. A second
   guard, `text-opacity.guard.test.ts`, freezes the dimmed-text debt per file
   and **derives** its floor from these same palettes rather than hardcoding
   one — re-tune a palette and the ratchet re-tunes with it.
2. **Blocking axe scans** — `apps/web/e2e/a11y/` fails on ANY critical/serious
   violation, `color-contrast` included, on login, dashboard, chat, settings,
   spaces and admin, plus reflow (320 CSS px) and 200 % zoom (640 px). Each
   run archives per-node JSON (selector, computed colors, font size/weight,
   observed vs required ratio) as report attachments.
3. **Browser matrix** — `.github/workflows/a11y-matrix.yml` replays the suite
   weekly on Chromium/Firefox/WebKit. The manual NVDA/VoiceOver campaign is
   `docs/a11y/AT_CAMPAIGN.md`.

### The blind spot of layer 2: surfaces that only exist while open

An axe scan sees the DOM it is given. A popup, a menu or a listbox that renders
only while the reader is interacting is **absent** from a scan that just loads
the page — so the forbidden-pattern list above is enforced on it by nobody.

Measured instance: the settings search results carried
`text-muted-foreground/80` on their description line, an alpha-diluted token the
list above forbids outright. It scored **3.51:1** against the popover
background at 12 px, under the 4.5:1 floor — and the existing
`settings page scans clean` journey never saw it, because the field was empty
when the scan ran. The fix was the plain token; the lasting fix is a second
journey that **types a query first**, then scans.

Rule: when a change introduces a surface that appears only on interaction, the
a11y journey covering that page gets a sibling that drives the interaction
before scanning. A scan of the closed state is not a scan of the component.

## Changing the palette

Edit `apps/web/src/styles/globals.css`, run
`pnpm exec vitest run src/styles/__tests__/design-contrast.guard.test.ts` —
the failure message lists every pair below threshold with its computed ratio.
The guard is the calculator: adjust until green, then run the axe suite for
the rendered proof. Never satisfy it by removing a pair from the matrix; add
pairs when components introduce new token combinations.

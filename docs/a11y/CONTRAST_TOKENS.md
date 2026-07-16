# Design-System Contrast Architecture (AC-002)

How LIA's theme tokens guarantee WCAG 2.x AA contrast across the 5 themes ×
light/dark — and how that guarantee is enforced so it cannot silently regress.

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
   for all 10 palettes, including hover blends and self-tints. Any palette
   edit below AA fails `pnpm test` before a browser ever renders it.
2. **Blocking axe scans** — `apps/web/e2e/a11y/` fails on ANY critical/serious
   violation, `color-contrast` included, on login, dashboard, chat, settings,
   spaces and admin, plus reflow (320 CSS px) and 200 % zoom (640 px). Each
   run archives per-node JSON (selector, computed colors, font size/weight,
   observed vs required ratio) as report attachments.
3. **Browser matrix** — `.github/workflows/a11y-matrix.yml` replays the suite
   weekly on Chromium/Firefox/WebKit. The manual NVDA/VoiceOver campaign is
   `docs/a11y/AT_CAMPAIGN.md`.

## Changing the palette

Edit `apps/web/src/styles/globals.css`, run
`pnpm exec vitest run src/styles/__tests__/design-contrast.guard.test.ts` —
the failure message lists every pair below threshold with its computed ratio.
The guard is the calculator: adjust until green, then run the axe suite for
the rendered proof. Never satisfy it by removing a pair from the matrix; add
pairs when components introduce new token combinations.

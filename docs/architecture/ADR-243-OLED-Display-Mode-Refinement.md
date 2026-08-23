# ADR-243: OLED display mode — a refinement of dark, selected by an attribute, not a fourth theme

**Status**: Accepted (2026-08-23)
**Deciders**: LIA core team
**Technical story**: UI review 2026-08-23 — "add an OLED mode with absolute black to the existing light/dark, and make the header icon cycle light → dark → OLED → light"

## Context

The product ships two display modes (`light`, `dark`, plus `system`) owned by
`next-themes`, and five colour accents owned by a separate `ColorThemeProvider`
that writes `data-theme` on `<html>`. Adding "absolute black" looked like a third
mode. It is not, and the difference is load-bearing.

`next-themes` applies the resolved theme by writing its **value** as a class:

```js
// node_modules/next-themes/dist/index.mjs
const v = d ? d[r] : r;
g === 'class' ? (P.classList.remove(...k), v && P.classList.add(v)) : …
```

`classList.add` takes a *single* token, so a `value={{ oled: 'dark oled' }}`
mapping throws `InvalidCharacterError`. `attribute` does accept an array, but
both attributes receive the same `v`. There is therefore no configuration of
`next-themes` that yields `class="dark"` **and** a distinct OLED marker.

A third theme value would consequently ship `class="oled"` *instead of*
`class="dark"`, and that removal is not cosmetic:

- **9 `resolvedTheme === 'dark'` call sites** would take their light branch —
  `CodeBlock` (syntax highlighting stylesheet), `MermaidDiagram` (diagram
  theme), `SnowfallEffect` (flake colour), `useLiaGender` (×3), `ThemeSelector`
  (accent preview). Light syntax highlighting on a black page; white diagram
  boxes; invisible snowfall.
- **9 `html:not(.dark) .cosmos` rules** in `globals.css` would match, sending
  the entire public site to its light variant.
- `color-scheme: dark` is declared inside the `.dark` token block, so native
  selects, scrollbars and date pickers would revert to the light palette.
  `next-themes` only assigns `style.colorScheme` for values in its
  `colorSchemes` list, so a third value would have left it stale rather than
  wrong-but-consistent.

## Decision

**OLED is a boolean refinement of dark, carried by its own `data-oled`
attribute on `<html>`, selected by `html.dark[data-oled]`.** `next-themes` keeps
owning `light | dark | system` unchanged.

### Why that selector

Specificity, and nothing else:

| selector | score | |
|---|---|---|
| `.dark` | (0,1,0) | base dark palette |
| `[data-theme='ocean'].dark` | (0,2,0) | accent × dark |
| `html.dark[data-oled]` | **(0,2,1)** | wins, **whatever the source order** |

A plain `.oled` class would score (0,1,0) and lose to every accent block —
silently, and only for users who picked an accent.

Requiring `.dark` in the selector is also what makes light mode immune with **no
application-side guard at all**: there is no code path that can forget it.

### The V3 display layer must be overridden separately

`globals.css` imports `lia-components.css` **without `layer()`**, so that file's
`.dark` block (24 `--lia-*` variables) is *unlayered* — and unlayered rules beat
`@layer theme` regardless of specificity. The OLED overrides for those variables
therefore live in `lia-components.css`, next to the values they replace. Without
that, chat cards would stay slate-blue (`#1f2937` on `#111827`) floating on an
absolute-black page.

### Palette

Six neutrals move; everything else is inherited:

```css
html.dark[data-oled] {
  --color-background: oklch(0% 0 0);   /* the point of the mode */
  --color-card:       oklch(17% 0.004 250);
  --color-popover:    oklch(20% 0.004 250);
  --color-secondary:  oklch(23% 0.005 250);
  --color-muted:      oklch(23% 0.005 250);
  --color-accent:     oklch(23% 0.005 250);
}
```

Each of the five accents keeps its own `primary` / `success` / `warning` /
`destructive`. `border` and `input` deliberately **inherit** the dark values:
measured, `oklch(32%)` reads better against absolute black (1.66) than against
the dark ground (1.48).

Surfaces are calibrated against the shipped dark mode rather than against zero,
so nothing separates *less* than it already does:

| pair | dark | OLED |
|---|---|---|
| card vs background | 1.09 | **1.10** |
| border vs background | 1.48 | **1.66** |
| border vs card | 1.37 | **1.51** |

All 25 contrast pairs × 5 accents are verified in
`design-contrast.guard.test.ts`, which now parses 15 palettes.

### Persistence

`users.theme` is `String(20)`, so `"oled"` — meaning "dark, with OLED" — needs
no migration. `system + OLED` is deliberately **not representable**: OLED is an
explicit choice, not something to inherit from the OS at dusk, and the Settings
switch is disabled outside an explicit dark mode rather than silently pinning a
mode the user did not ask for.

The field *is* validated, by `validate_theme_field` in
`domains/shared/schemas.py` — several files away from its declaration. Shipping
the frontend value without adding it there produced a **silent** failure: the UI
applied the change locally and only the PATCH answered 422, so the screen turned
black and nothing looked wrong until the next reload. A cross-layer guard now
reads `PERSISTED` out of `theme-mode.ts` and compares it to `VALID_THEMES`.

### The header cycle drops `system`

Three predictable stops beat four the user cannot anticipate, and a circular
control that sometimes lands on "follow the OS" reads as broken when the OS is
already on the mode you just left. The cycle is driven by the **resolved**
appearance, not the stored value — reading the stored one classified `system` as
"not dark", so a user on a dark OS pressed once and saw nothing change.

`system` is the column's `server_default`, so Settings must keep offering all
four choices; without that panel one press of the header toggle would lose it
for good.

## Consequences

- Zero change to `next-themes` configuration, and zero change to the 18 sites
  that read `resolvedTheme` or `html:not(.dark)`.
- OLED overrides live in two files (`globals.css` for `--color-*`,
  `lia-components.css` for `--lia-*`) because the cascade requires it. The
  reason is documented in both.
- The theme change is applied inside a single View Transition, feature-detected
  and skipped under `prefers-reduced-motion`. `disableTransitionOnChange` only
  wraps `next-themes`' own `setTheme`, so the attribute write carries its own
  transition suppression.
- Theme writes are serialised and coalesced: three quick presses used to race
  three PATCHes to the same row with no ordering guarantee.

## Alternatives considered

- **A third `next-themes` value.** Rejected on the evidence above: it removes
  `.dark` and silently flips 18 branches.
- **`value={{ oled: 'dark oled' }}`.** Not possible — `classList.add` rejects a
  token containing whitespace.
- **`attribute={['class', 'data-mode']}`.** The provider is genuinely
  array-capable, but both attributes receive the same value, so the pair is
  `class="oled" data-mode="oled"` — the `.dark` removal is unchanged.
- **A `.oled` class instead of an attribute.** Loses to every accent block on
  specificity, for accent users only.
- **Making `background` the only override.** Rejected: cards at the dark 22%
  against a pure-black page separate *worse* than they do today (1.04 vs 1.09),
  so the mode would have degraded legibility in exchange for depth.

## References

- `apps/web/src/lib/theme-mode.ts` — the state machine and the persistence contract
- `apps/web/src/hooks/useThemeMode.ts` — single owner of the display state
- `apps/web/src/components/theme-init-script.tsx` — pre-paint attribute application
- `apps/web/src/components/settings/DisplayModeSelector.tsx` — the four-way choice
- `apps/web/src/styles/__tests__/design-contrast.guard.test.ts` — 15 palettes
- `apps/api/tests/unit/domains/users/test_theme_preference_contract.py` — the cross-layer guard
- ADR-171 (`position: sticky` and the `overflow-x: clip` page contract)
- ADR-184 (an enforced constraint must be published to whoever produces the value)

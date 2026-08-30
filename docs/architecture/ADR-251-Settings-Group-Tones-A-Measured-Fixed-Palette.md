# ADR-251 — Colour cannot separate a repeated shape: the settings group tones

- **Status**: Accepted
- **Date**: 2026-08-30
- **Related**: ADR-227 (settings master–detail shell), ADR-243 (OLED depth),
  ADR-206 → ADR-208 (design-system consistency), ADR-184 (an enforced
  constraint must be published to whoever produces the value),
  WCAG 1.4.1 (use of colour), 1.4.11 (non-text contrast)

## Context

The settings shell (ADR-227) lists **53 sections** under **12 group headings**,
in two places: the overview cards and the permanent rail.

Every one of those 53 rows drew its glyph in `text-primary` on a
`bg-primary/10` chip. The list was therefore uniform in colour — and it was
worse than that: an audit of `settings-section-icons.ts` found **16 sections
sharing a glyph already used by another section**. `Plug` alone served four
different settings.

So the eye had exactly one repeated shape, in one repeated colour, to navigate
a list of fifty-three entries. The search field (ADR-172) was the only real
affordance, and a search is what you use when looking has failed.

## Decision

### 1. Two defects, two fixes — colour is not one of them

**Colour does not repair a repeated shape.** Two plugs remain two plugs, even
in two colours: a reader who has learned "the plug one" still cannot tell which
plug. The glyph collisions were therefore fixed first and independently — a
distinct drawing per section — and the tone was added on top of a list that had
already become legible without it.

One collision is kept, and recorded in the registry: the two consumption
exports render through a single component that switches on its mode. Giving
them two drawings would require a shape the "exactly one icon per file" guard
cannot read, and they live in different tabs.

### 2. A tone per GROUP, never per item

Twelve colours are a map the eye learns. Fifty-three would be noise it
deciphers — and no reader can hold fifty-three hue↔meaning pairs. The tone is
therefore carried by the **group**, and an item inherits it.

`toneForSection` is the single rule, shared by the overview card and the rail
row. Two lookups would let one list disagree with the other about a section.
A caller outside the table falls back to the accent, never to nothing.

### 3. Tokens, not utility classes — because that is what the guard reads

The palette is **fixed**: it does not follow the accent the user picked. That
is the product's **second** such deviation, after the cyan skill badge, and it
is deliberate — a map whose colours move with a preference is not a map.

Written as literal Tailwind colours it would have sat **outside** the contrast
guard, which reads `--color-*` token pairs. That is exactly the hole `badge.tsx`
records for the fixed badge variants it removed. Written as
`--color-settings-*`, the palette falls inside the guard by construction:
24 tokens, 12 in `@theme` at L=55 %, 12 under `.dark` at L=72 %.

Two lightnesses are required, not stylistic: a single value cannot clear 3:1 on
both a near-white and a near-black card.

### 4. What measurement said, twice, against the intuition

The first palette was the obvious one — twelve hues 30° apart, one shared
chroma. Neither half survived:

- **sRGB's gamut is not a cylinder.** At L=55 % a violet holds 0.25 of chroma
  and a teal only 0.09. A shared chroma put **6 of the 24 tones outside sRGB**,
  where the browser clamps them — rendering neither the hue nor the chroma
  declared, and silently breaking the one promise the fixed lightness exists to
  keep. Each hue now carries the most chroma sRGB allows it at that lightness,
  less a 6 % margin.
- **Even spacing is not perceived spacing.** Once chroma follows the gamut, two
  pairs landed **0.116 apart** — under the 0.12 distinctness floor the guard
  itself imposes. The twelve angles are therefore **searched**, on the **worse
  of the two modes**: the two lightnesses cut different gamut slices, and a set
  optimised on light alone still left a pair at 0.113 in dark. Closest pair
  now **0.199**.

Both facts are enforced, not remembered: the contrast guard measures the tones
on the two grounds they actually sit on — the card chip (tone at 12 % over
`card`) and the bare rail (`background`, plus the `accent/60` hover blend) —
across all 15 palettes, and the distinctness check runs in both modes.

Worst measured: **3.64** on the chip and **3.45** hovered, against a 3.0 floor.
The glyph is a non-text graphical object (WCAG 1.4.11), so 3:1 is the correct
floor — not 4.5.

### 5. Colour is decoration and grouping, never state

The open rail row is still marked by its background, its weight and the accent
ink; a capability's on/off is still a filled or hollow dot. Nothing became
knowable only through hue (WCAG 1.4.1): a reader who does not perceive these
twelve tones loses no information at all.

### 6. The open section's header keeps the accent

Consequence, accepted rather than discovered: the same glyph is drawn in its
group tone in the list and in `text-primary` in the opened pane. `apps/web/CLAUDE.md`
rules that a title icon is in the theme colour, and a section header is a title.
The two surfaces are never displayed together.

## Consequences

- **Positive** — a section already visited is found by its appearance rather
  than by reading; the group headings gain a visual counterpart; the palette is
  measured by the same guard as every other colour in the product.
- **Positive** — the glyph audit removed 16 semantic collisions that no test
  could have caught, since each icon was individually valid.
- **Cost** — a fixed palette is one more thing that does not follow the theme,
  and a reader must be told so; it is documented in `docs/a11y/CONTRAST_TOKENS.md`
  beside the badge exception rather than in a skill file.
- **Cost** — adding a settings group now means adding a hue, and the hue must be
  searched against the existing eleven rather than picked. The guard makes that
  a build failure instead of a review comment.

## Alternatives rejected

| Alternative | Why not |
|---|---|
| A tone per SECTION (53 hues) | No perceptual room: sRGB cannot hold 53 distinguishable hues at one lightness, and no reader learns 53 pairs. |
| Follow the accent, vary only lightness | Twelve steps of one hue are a gradient, not a map; and the accent is user-chosen, so the map would move. |
| Colour the open row's glyph too | Would make hue compete with the accent as the "current" signal — colour would start carrying state. |
| Literal Tailwind colours | Outside the contrast guard. Measured once already: the fixed badge variants had to be removed for exactly this reason. |
| Hand-picked hues, reviewed by eye | Six of the first twenty-four were outside sRGB and looked plausible in review. Only measurement saw it. |

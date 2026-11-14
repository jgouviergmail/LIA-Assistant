# ADR-377 — The account chooses how the interface is drawn: one icon door, three styles, and hours for black

**Status**: Accepted, 2026-11-09.
**Date**: 2026-11-09

**Amends**:
[ADR-207](ADR-207-An-Action-Has-An-Altitude.md) — a selected or busy control keeps a visible
state whatever the colours of its icon.
[ADR-332](ADR-332-Deterministic-Cards-Received-Facts-And-Message-Owned-Actions.md) — the
`material-symbols` markers of new and archived cards are drawn in the account's icon style.

## Context

Two requests reached the same place, the account's appearance.

- **Icons.** The interface drew every symbol with one monochrome line set. The owner asked for
  colour, and for the choice to stay the person's. More than six hundred files imported their
  icons straight from the vendor package, so a style could only be a rewrite of every import.
- **Light and black.** The theme already cycled light, dark and absolute black for OLED screens,
  by hand. People who read LIA at night asked for black to come by itself at an hour they set.

Both are display preferences: they must follow the account from one device to the next, cost no
model call, write nothing on their own, and keep the accessibility the interface already had.

## Decision

1. **One door for every icon.** Application code imports icons from `apps/web/src/lib/icons`,
   generated from a reviewed catalogue (`scripts/icons/`). Only this facade imports the vendor's
   line artwork; the generator's check mode refuses any other import. `createAppIcon` keeps each
   icon's dimensions, refs, labels and events, and reads the account's style from context.
2. **Three styles, one meaning.** `users.icon_style` holds `lucide`, `fluent` or `flex`, refused
   otherwise by a database CHECK and by the API's closed vocabulary; every account starts on
   Fluent Color. A correspondence keeps the object, the action, the direction and the state: an
   approval badge is not a thumbs-up, a cancelled calendar is not a calendar. Where a collection
   lacks a concept, an attributed LIA complement fills it; nothing falls back silently to the
   monochrome set. Fill and selection stay semantic states, read from the SVG's fill, never
   inferred from class names.
3. **Vendored, pinned, credited.** The vendor inputs are checked in with their package
   coordinates, SHA-512 digests and licences (MIT for Fluent, ISC for Lucide, CC BY 4.0 for
   Streamline Flex), credited in `public/icon-licenses.txt` and linked from the selector. The
   application never downloads an icon at runtime.
4. **Accessibility first.** The system's forced-colours mode draws the original line glyph in
   system colours. A selected or busy control keeps an ARIA state and a visible indicator that
   the icon's own colours cannot erase.
5. **Automatic appearance by the civil clock.** The theme vocabulary gains `auto`. Two minutes
   of the civil day, in the account's time zone, bound a half-open light interval that may cross
   midnight; the rest is absolute black. The profile service merges a partial change under a
   fresh row lock before validating it, and database constraints hold the bounds. In the
   browser, one provider owns the clock, the account synchronisation and the serialised writes;
   a clock tick changes the rendering only, never the profile. The pre-paint script runs the
   same pure resolver as the runtime, so the first frame is already right. Cycling the theme by
   hand leaves automatic mode.

## Consequences

- Every account, existing ones included, sees Fluent Color after the upgrade; Lucide is one
  click away in **Settings › Appearance**.
- A new symbol is a catalogue entry, reviewed and regenerated, never a direct vendor import.
- Updating a vendor collection means verifying its archive, reviewing the diff and regenerating.
- Automatic appearance never writes the profile from a timer, so two devices of one account
  cannot fight over the theme, and a failed choice stays local and says so.

## Amendment 2026-11-11 — an object no collection draws

In the colour styles the radio drew Lucide's broadcast, the glyph the live voice and the signal
controls also carry, and the recorder a disc nobody read as recording. Owner decision: the radio
shows a radio set wherever it is named, the recorder the red recording dot.

- A **LIA concept** (`LIA_CONCEPTS` in `scripts/icons/catalogue.mjs`) is a facade name of its own
  for an object none of the three collections draws. LIA draws it outright in both colour styles,
  the line style keeps the Lucide glyph the declaration names, and the manifest files it as
  `lia-concept`. `RadioSet` is the first; `Radio` stays the broadcast.
- In the line style the two names draw one glyph, so the wrong one is invisible there: a module
  showing the broadcast declares what it means by it (`radio-glyph.guard.test.ts`), and every
  other surface that names the radio imports the set.
- `Disc` is the recording dot: red at rest as well as live, its ring's colour and pulse still the
  caller's.

## References

- [ICON_STYLES.md](../technical/ICON_STYLES.md), [DISPLAY_PREFERENCES.md](../technical/DISPLAY_PREFERENCES.md),
  [scripts/icons/README.md](../../scripts/icons/README.md)
- `apps/web/src/lib/icons/index.ts`, `apps/web/src/components/icons/create-app-icon.tsx`,
  `apps/web/src/lib/theme-schedule.ts`, `apps/web/src/lib/theme-preferences.tsx`
- Migrations `a4c92e7b6d81` (icon style) and `b74d02e6a193` (appearance schedule)

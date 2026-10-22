# ADR-356: Responsive Position details and shared place numbers

**Status:** Accepted

**Date:** 2026-10-19

## Context

The explicitly activated Position map from
[ADR-352](ADR-352-Position-Before-Places-In-Every-Display-Mode.md) and its
[acquired details and selected journey](ADR-355-Acquired-Place-Details-And-Accounted-Selected-Routes.md)
must remain readable on a phone and easy to match with the list. Reserving an
empty map before activation wastes space. Constraining rich details inside two
nested scrolling containers hides content and makes touch navigation awkward.
An accessible marker title alone does not give sighted readers a visible way to
match a pin with a list entry.

## Decision

Keep a compact Position section with its source list, activation action and
disclosed cost. Mount the interactive map after the existing explicit paid
admission; do not reserve a tall empty canvas before activation. Configuration
and provider failures keep a readable explanation and the source links.

Selection from the list or a marker opens the same details and selects the same
place. Desktop uses the map's native anchored InfoWindow, with the title in its
header and the native body as its only vertical scrolling region. On narrow
screens, use the application's modal Dialog near the bottom of the viewport,
bounded by the visible height and safe area. One body contains its title and
facts and owns scrolling. The shared dialog supplies modality, dismissal and
focus handling; the selected entry regains focus when still mounted. Switching
presentation or destroying the map clears native content and listeners.

Derive one visible, one-based number from each place's position in the existing
ordered Position payload. Reuse that number in the list and in the marker's
visible pin and accessible title. Numbering belongs to the answer's selection,
not to the filtered set of mappable coordinates: an unlocated entry retains its
number and source link, so later pins may have gaps. Overlapping markers keep
their own identities. Compact list badges and native `PinElement.glyphText` pins
use the `primary`/`primary-foreground` theme tokens, keeping the same visible
identity beyond colour; pins attach through the current DOM API rather than
deprecated `content`/`element` properties. Numbers do not become provider IDs,
reorder places or create another search. The source list remains the
keyboard-accessible path to every located selection.

## Alternatives considered

- A permanently reserved map stage leaves blank space before consent and when
  configuration is absent.
- One desktop-sized anchored popup at every viewport size restricts phone
  content; separate phone facts would create two presentations to maintain.
- An inner details scroller inside the native popup adds a second scrollbar.
- Independently numbering the list and filtered markers shifts identities as
  soon as one place lacks coordinates.

## Consequences and verification

The same facts and route state feed both presentations. Viewport changes affect
their container, while source order supplies the identity across list and map.
Google's native popup DOM remains an integration boundary: its body owns desktop
scrolling and requires browser verification after SDK or layout changes.

The [Position component](../../apps/web/src/components/chat/markdown-place-position.tsx),
[popup](../../apps/web/src/components/chat/place-map-popup.tsx) and
[map adapter](../../apps/web/src/lib/google-place-map.ts) implement the boundary.
Unit tests cover shared numbering, unlocated entries, list/marker selection,
focus and cleanup. The
[browser journey](../../apps/web/e2e/smoke/chat-position-classification.spec.ts)
checks desktop and narrow layouts, explicit activation and reachable details
with controlled SDK/API responses. This proves LIA's layout and lifecycle under
those fixtures; it does not qualify live Google tiles or real-provider billing.

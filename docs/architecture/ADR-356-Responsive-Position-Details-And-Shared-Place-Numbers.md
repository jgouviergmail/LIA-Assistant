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

## Amendment 2026-10-22 — the list beside the map, a centred offer, details re-placed after a fit

Owner requests of 2026-10-22, in the Position component, its map adapter and
`lia-cards.css`:

- `data-map-shown` (loading or ready) decides the list's layout. On a card at
  least 45rem wide (`@container card`) the places sit in a column beside the
  map, sized by the map alone and centred on its height by auto margins — a
  list longer than the map scrolls inside that height from its first place,
  which `justify-content: center` would have pushed out of reach. Without a
  map — behind its offer, unavailable, failed, or the server's fallback list —
  they read as a line that wraps, centred, and starting at the left edge on a
  phone (`max-width: 639px`, the details' own phone breakpoint).
- The offer is one centred block: the button, then its cost on a line of its
  own in an 11 px type. The reading order stays the DOM's.
- The stage wears the panel's corner radius (`--lia-radius-lg`).
- The details window is re-placed after every fit (`revealDetails`). The map
  pans a window into view when it opens; a fit moves the map, never the window.
  A first selection's route comes back from the network after its details
  placed themselves, and its fit left them badly placed; a second selection,
  whose route comes from the cache, fitted first. The re-opening holds the
  person's dismissal callback aside, as `clearDetails` does, and leaves alone a
  window holding the focus. It relies on the SDK firing `close` synchronously,
  which the second selection shows: it closes then re-opens with a new
  callback, and would otherwise dismiss itself.

Inferred from that evidence, not measured on live Google tiles: a paid
verification remains. Unit tests pin the attribute and the four re-placement
cases, and `styles/__tests__/chat-layout.guard.test.ts` the list's placement on
the CSS text. The placement was measured in the dev browser with the map-shown
state set in the DOM and no map loaded: the list's middle on the map's (447 px
both), a fifteen-place list scrolling from its first place to its last, three
places at the left edge of a 388 px phone frame. The browser journey below was
not re-run for this amendment (it builds the application, which the owner's
rule keeps off the workstation).

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

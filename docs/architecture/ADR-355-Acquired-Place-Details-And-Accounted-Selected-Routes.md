# ADR-355: Acquired place details and accounted selected routes

**Status:** Accepted

**Date:** 2026-10-19

## Context

The Position card from [ADR-352](ADR-352-Position-Before-Places-In-Every-Display-Mode.md)
already knows the places selected for the answer. Opening a marker should expose
those facts and one useful journey without another Places search, a model call,
or an unaccounted browser request to the Routes API. A saved position must remain
recognizable as dated, and a walking journey longer than the person's chosen
limit must not be presented as the walking option.

## Decision

Project bounded, already acquired address, rating, review count, phone, website
and opening hours into the versioned Position payload. Missing facts remain
absent; provider trees and credentials do not enter the archive. The frontend
continues reading the earlier payload version and renders the same validated
details from a marker or its source-list entry. Opening details never refetches
Places.

An explicit selection calls the authenticated
`POST /connectors/google-maps/place-route` endpoint with the selected coordinates
and an optional browser origin. The server owns origin and travel-mode selection.
Reuse the existing location cascade: consented browser position, fresh opted-in
last-known position, then configured home. Browser coordinates and capture time
are bounded by the [request schema](../../apps/api/src/domains/connectors/place_route_schemas.py),
including bounded future clock skew. The response names the chosen source and
carries `origin_as_of` for last-known positions; the UI shows its age instead of
calling it current. Without an origin, return
`detail.code = place_route_origin_unavailable` and keep the acquired details usable.
The browser reads location only when the application preference and an existing
browser permission allow it; selection does not open a permission prompt.

For this selected-place surface, initially choose WALK when the origin-to-place
haversine estimate is **at most 2 km, inclusive**, and DRIVE above it. Validate the
returned route before using its facts. A valid WALK route of at most 2,000 metres
is retained; if its actual Google distance exceeds that limit, compute DRIVE
once instead. There is no mode chooser or pair of displayed alternatives. The
correction shares the overall deadline and allows at most two route computations;
invalid paid payloads do not trigger a correction. Generic assistant route-tool
defaults keep their existing policy. The
[selected-route service](../../apps/api/src/domains/connectors/place_route_service.py)
is the authority for this rule.

Each request owns a separate `place_route_*` tracking run. Reuse the server key,
Google Routes client, feature-derived SKU pricing, administrator switch, user
rate limit, and platform/user spend ceilings. No database transaction stays open
during provider I/O. Before a corrective DRIVE call, strictly commit the paid
WALK call, recheck access and ceilings, and preflight the actual DRIVE SKU.
Incremental and final commits file each paid call once, including an unusable
response or cancellation. Registered cancellation settlement finishes accounting,
closes the client and releases run records. A persistence failure cannot acknowledge
a successful route. The frontend bounds and deduplicates repeated selections
with its short-lived, account-scoped cache and discards obsolete responses.

## Alternatives considered

- Refetching place details on each click adds latency and paid work for facts
  already acquired; projecting the existing facts keeps their provenance.
- Calling Routes directly from the browser cannot enforce LIA's account ledger,
  origin policy and quotas at the provider boundary.
- Choosing WALK from straight-line distance alone mislabels detours. Requesting
  both modes every time spends unnecessarily; one conditional correction bounds
  that extra work.

## Consequences and verification

Selection may pay for a WALK attempt and its DRIVE correction. If the second
request is refused or fails, the first remains accounted and the details remain
available with a route explanation. A dated or home origin is explicit.

[Route tests](../../apps/api/tests/unit/domains/connectors/test_place_route.py)
cover origin validation, mode boundaries, provider errors and cancellation.
[Accounting tests](../../apps/api/tests/unit/domains/connectors/test_place_route_accounting.py)
exercise the real tracker and client with simulated provider/DB boundaries,
including distinct WALK/DRIVE SKUs, quota refusal and repeated cancellations.
Projection, hook and browser tests cover old archives, details, stale responses
and permission handling. These tests do not measure a real Google route or bill.
See [HTML cards](../technical/HTML_CARDS.md) and the responsive presentation
decision in [ADR-356](ADR-356-Responsive-Position-Details-And-Shared-Place-Numbers.md).

# ADR-352: Position before places in every display mode

**Status:** Accepted

**Date:** 2026-10-19

## Context

A list of Google Places is easier to compare geographically on one map.
Requiring a particular response format hides that context from people who
prefer HTML or Markdown. Loading an interactive map automatically would spend
and contact Google before the person chose to activate it.

## Decision

For a new answer containing selected native Google Places, project one bounded
Position card before the individual place cards in every display mode. Keep
the native places and coordinates as the source of truth; do not geocode names
again or infer places from generated prose. Include a usable source list when
coordinates or interactive configuration are missing.

The card appears automatically. Its click discloses the current cost and obtains
the existing server-side Maps admission before loading the shared Google Maps
SDK. Reuse the routes map loader, account ownership fencing and payment ledger.
One map activation owns one admission; remounts, concurrent loaders and late
callbacks cannot bill or publish into another account. Markers, overlapping
locations and viewport fitting use the selected coordinates. Bounded fallback
content covers missing coordinates or display limits.

The operator explicitly provides a browser key and Cloud map ID. Browser
credentials need provider restrictions; they are visible by design. A DEV
demonstration map ID is never accepted as production configuration. An unavailable
configuration renders a compact, informative state rather than a blank stage.

## Consequences and verification

This changes the layout of newly generated answers; it does not rewrite
historical answers. There is no new model call, search, memory or LangGraph key.
Native API/ledger tests and browser journeys cover owner changes, cost refusal,
network failure, keyboard activation, narrow screens and reduced motion.
Browser tests control SDK and API responses; they do not prove Google's actual
tile delivery or charge on a real browser key.

See [HTML cards and map configuration](../technical/HTML_CARDS.md).

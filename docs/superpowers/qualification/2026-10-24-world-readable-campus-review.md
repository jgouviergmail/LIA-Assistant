# Readable campus and spatial activities — qualification

This extends the [G13/G14 cold review](2026-10-24-world-immersive-cold-review.md)
under the [readable campus specification](../specs/2026-10-24-world-readable-campus.md).
It is an inline worktree delivery, not a merge, deployment or declaration of final
artistic acceptance.

## Delivered design

The continuous campus now provides twelve themed places, camera exploration and
a localized place directory. Mail, agenda, telephone, journal, interests and Radio
have distinct authored objects. All functional bindings use stable semantic keys,
so rearranging furniture does not change its activity. An object is identified
before activation by its contextual label and pointer feedback. Approaching it
uses the existing collision model and rechecks availability on arrival.

A person can be approached for a private conversation. Seating and lying use
server-authoritative pose slots, including occupancy, reconnect, standing and
private-bedroom exclusion from shared snapshots. These controls supplement the
accessible native interfaces; they do not replace server authorization.

Architecture now has bounded plaster, oak, brick, glazed, acoustic and slate
families. Joint caps use the same material family as their walls. Open bookcases,
a brass telescope, postal objects, a calendar, a clock, a writing desk, a meeting
table, a herbarium and a receiver have their own geometry. Fountain animation is
bounded and respects reduced motion. The LIA facial atlas is retained.

## Findings fixed during adversarial review

- A pending movement acknowledgment could follow a pose request and immediately
  stand the avatar. Pose admission now waits for the synchronizer to settle; the
  server still verifies the actual approach position and sole seat occupancy.
- Old ephemeral positions could belong to changed geometry. Runtime state keys
  include scene identity; old keys expire without a shared-cache flush.
- A hand-built place list could open beneath the action bar. The native portalled
  menu now owns keyboard navigation, focus return and layering. Real hit-target
  tests also caught overlaps on short landscape and enlarged small-phone layouts.
  Compact contextual icons preserve full accessible names and minimum targets.
- Firefox's first window-focus event could hide the public alias field before its
  input event. Admission is now outside the private account guard. The connected
  world, private panels and account-switch withdrawal remain inside that guard;
  ticket identity is independently checked on the server.
- Restoring reading history after one animation frame was not sufficient for a
  resumed private portal. A scoped resize observer restores from the owner store
  after actual layout changes and never records an intermediate zero clamp.
  Explicit “latest messages” still resumes following.
- Additional architectural conditions crossed the existing complexity ceiling.
  Window joinery is a separate painter; the ceiling was not raised.

- The final night captures revealed phantom window light on acoustic panels.
  Joinery and lighting now share the same authored window predicate.
- Rain previously inferred shelter from wooden flooring. Covered places now
  declare shelter explicitly; rain and snow respect it on every material, while
  exposed wooden decking remains outdoors. Nine regression cases failed before
  the correction and pass afterward. Collision and pose data are byte-for-byte
  equivalent to the preceding catalogue.

## Evidence and limits

The optimized G17c interaction snapshot and final G17d atmosphere correction passed the following measured checks. Publication and performance evidence are recorded in the
[evidence manifest](assets/world-readable-campus-g17/manifest.json).
Intermediate failed runs remain local and do not count as successful qualification.

| Check | Measured result |
| --- | --- |
| World frontend regression tests | 212 passed in 40 files after the final weather correction |
| Backend world unit and real Redis integration | 133 passed |
| Native Chromium, Firefox and WebKit journeys | 18 passed, no retry or skip |
| Browser artwork, input, activities, LIA, responsive and accessibility | 71 passed; 4 explicit Chromium-only variants skipped in the other engines |
| Optimized Next build and TypeScript | Passed |
| Frontend lint, accessibility, hooks and complexity ratchets | Passed, existing ceilings retained |
| Six-language key parity | Passed |
| Documentation preview and diff whitespace | Rechecked after the final evidence update |

The native browser result includes the previously failing Firefox history
restoration and admission cases. Every small-layout correction was replayed
against the actual optimized stylesheet, not the injected preflight stylesheet.
The worktree and candidate hashes match across all world sources and locales.
The repository's pre-existing hook/complexity baseline remains; passing the
ratchet does not mean that unrelated baseline debt disappeared.

Native journeys use isolated accounts, SQL and Redis. They exercise real message
delivery, reciprocal replies, interrupted reads, a lost acknowledgment, reload,
account changes, private memory mutations and third-account denial. Translation
uses an explicit inert fixture: those results do not establish supplier translation
quality or actual paid-provider costs.

The full frontend coverage run passed before the last admission, layout and
scroll-restoration corrections; those later changes have their own regression
tests and browser replay. Physical Raspberry Pi and low-end phone performance
remain unqualified. Emulated viewports and CPU slowdown are separate evidence.

## Final publication and performance

The usable development preview is
[the shared world](http://127.0.0.6:3010/fr/world-preview?shared=1&resume=1).
Final native entry, camera exploration, object hover and phone directory were
replayed after publication. The final atmosphere delta passed another 30 browser
cases across the three engines. The published source matches the final worktree
hashes. The optimized anonymous preview remains unavailable by design.

The final optimized measurement recorded 54.5 FPS on desktop, 29.8 in the phone
viewport at economic quality and 24.3 with CPU slowdown multiplied by four.
Decoded textures were approximately 41 MiB and 34 MiB respectively. These are
samples on this host, with five native server clients and one full UI renderer;
host load was not controlled. The preceding snapshot measured higher values.
These results do not establish a physical-phone or Raspberry Pi frame guarantee.

Review the actual [postal space](assets/world-readable-campus-g17/campus-post.png),
[radio studio](assets/world-readable-campus-g17/campus-radio.png),
[greenhouse](assets/world-readable-campus-g17/campus-conservatory.png),
[phone directory](assets/world-readable-campus-g17/campus-mobile-directory.png)
and [seated pose](assets/world-readable-campus-g17/garden-seat.png).

## Docker cleanup

The [cleanup record](assets/world-readable-campus-g17/docker-cleanup.json) records
31 removed obsolete containers, six discarded preview builds and one unreferenced
old Redis volume. The four services needed by the working preview remain.
Shared dependency volumes, base images and the shared BuildKit cache are retained;
no dedicated task image or builder was found.

One disposable qualification API container remains blocked: Docker reports that
it tried to kill the container but received no exit event. Its readiness process
was observed in Linux D state. A global Docker/WSL restart was not attempted because
the owner is concurrently using main and another session.

## Acceptance boundary

The new campus is a reviewable iteration. The owner has not accepted the artistic
finish as final. Larger rooms alone are not sufficient: object density, decoration,
atmosphere and discoverability must continue to be assessed in actual play.

The accepted V1 exclusions remain voice, time-limited guest invitations, shared
furniture dragging and federation. No navigation, hover, artwork, pose or camera
operation calls an LLM. Native panels retain existing ownership, feature flags,
HITL, quotas and billing.

The rapid publication-only conversation subset hit the existing server write
limiter on its third browser because it reused the same two accounts in less than
one limiter window. Chromium and Firefox passed; WebKit passed after natural
expiry. No limiter, quota or Redis state was weakened or flushed. The full native
suite already passed all three engines without retry.


## Owner feedback after publication

G17 was not accepted as the target art direction. The owner found the campus too spread out, rooms too large and sparsely furnished, and colours too muted. Its passing functional evidence does not constitute visual acceptance. The [connected house revision](../specs/2026-10-24-world-connected-house.md) supersedes that spatial direction; retain this report as historical evidence.

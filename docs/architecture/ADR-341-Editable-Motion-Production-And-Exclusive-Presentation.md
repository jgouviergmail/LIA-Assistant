# ADR-341 — Editable motion production and exclusive presentation

**Status:** Accepted — implemented; exported media are qualified separately.
**Date:** 2026-10-12
**Scope:** Product film authoring, faithful demonstrations, reproducible delivery and public playback.

**Related:** [ADR-330](ADR-330-Landing-Media-Served-Without-Runtime-Work.md)
and [motion production guide](../technical/MOTION_DESIGN.md).

## Context

The public landing needs a complete product presentation and distinct feature
focuses. A video editor project detached from application sources drifts as the
product evolves. Animating invented interfaces makes demonstrations misleading;
moving an entire screen without directing attention also reduces readability.
Authoring tools and large media must remain outside the deployed application.

## Decision

1. **Author a deterministic offline React composition.** A separate pinned
   Remotion project in `tools/lia-motion` owns chapter timing, HTML/CSS views,
   typography, native companion poses and measured musical accents. The
   application bundle and Docker build context exclude this authoring project.
2. **Use native sources as the visual contract.** Reconstructed views cite
   application components, styles, labels and reference captures. Their data
   are fictitious. They retain native UI status colors, while editorial text
   uses the LIA blue/violet palette. Demonstration controls have no backend
   side effects. Availability and unillustrated capabilities stay explicit in
   the coverage report; assigning a feature key is not proof of visual coverage.
3. **Keep screen geometry stationary.** The complete native view has a fixed
   frame, scale and held state. An explicit focus reveals a crop of declared
   native elements at a fixed position, without reflowing or replacing rows.
   DOM geometry sampled from rendered compositions checks this independently
   of timing tests. BIP accompanies the presentation outside the native screens;
   native avatars and their expressions have a dedicated sequence.
4. **Preserve several editorial outputs from one construction.** The complete
   film, explicit shorter landing cut, feature focuses and 25 fps working master
   share the same chapter definitions. Cut points follow measured audio accents;
   a prompt's BPM is not treated as a measured constant tempo. Offline audio
   preparation reuses archived recordings and makes no paid generation call.
5. **Qualify actual delivered bytes.** Render receipts and source fingerprints
   identify the revision. Packaging creates immutable hash-named web assets,
   native manifests and bounded beat maps. Verification parses application
   schemas and measures streams, duration, color metadata and encoded loudness.
   The editable archive checks every member hash and excludes secrets/caches.
   Technical qualification does not replace continuous editorial/audio review
   or a broadcaster's own acceptance specification.
6. **Expose the full film explicitly.** An optional `presentation` descriptor in
   the operator-hosted manifest names the complete film. It is separate from
   automatic playlist selection. The blue Presentation CTA opens a lazy-loaded
   fullscreen dialog using the existing accessible dialog primitive. While
   open, the background player is suspended, including audible playback;
   closing restores its prior eligible playback state and keyboard focus.
   Metadata requests are same-origin public UI reads, abortable and bounded.
   Explicit Retry uses a fixed no-store refresh route; server-side singleflight
   and a bounded cooldown protect the configured origin. Ordinary reads retain
   their positive and negative caches; clients cannot choose another origin.

## Consequences

Product updates can change a chapter or focus while keeping the rest of the
editable production. A faithful recreated interface still requires a review
against the current product; fixtures do not prove real provider, installation,
push delivery or production execution. The current film is French. Localized
CTA, dialog and disclosure texts cover the application's six languages; they
do not make the media itself multilingual.

Music recordings, requests without credentials, provenance and applicable
provider terms remain with the construction. No exclusive music copyright or
broadcast acceptance is inferred. Native resources keep their original paths
and licensing. Superseded render caches can be removed after retaining the
active delivery and checked source archive.

## Verification and evolution

Run `task motion:check`, rendered DOM geometry review, representative stills,
continuous playback review, packaging and delivered-file verification after
changes. Frontend tests separately cover explicit media selection, public
transport, fullscreen lifecycle, background suspension and six-language copy.
The [production procedure](../technical/MOTION_DESIGN.md) describes selective
rerendering, publication order, preservation and rollback.

# Motion production and evolution

**Last reviewed:** 2026-10-12

The editable product film lives in [tools/lia-motion](../../tools/lia-motion/README.md).
It is an offline HTML/CSS/React Remotion construction. It shares native artwork,
expression recipes, typography and source contracts with the application, while
keeping dependencies and generated media outside the deployed frontend.
[ADR-341](../architecture/ADR-341-Editable-Motion-Production-And-Exclusive-Presentation.md)
records the authoring and exclusive playback decisions.

## Construction and ownership

| Source                                                                          | Responsibility                                                                                          |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `tools/lia-motion/src/presentation-plan.ts`                                     | Active revision, chapter story, explicit landing cut, feature focuses, source evidence and availability |
| `tools/lia-motion/src/PresentationFilm.tsx` and `presentation-film.css`         | Composition, fixed native frames, focus crops and editorial text                                        |
| `tools/lia-motion/src/presentation-geometry.ts`                                 | Fixed frame geometry, declared focus bounds and crop opacity                                            |
| `tools/lia-motion/src/presentation-timing.ts`                                   | Deterministic musical cut positions at each frame rate                                                  |
| `tools/lia-motion/src/FeatureScreens.tsx`, `FaithfulUi.tsx`, `ProductStory.tsx` | Faithful native layouts with fictitious scenario data and source metadata                               |
| `tools/lia-motion/src/AvatarDemonstration.tsx` and `StoryMascot.tsx`            | Complete native avatar catalogue, contextual expressions and BIP's presentation acting                  |
| `tools/lia-motion/src/music-v5.json` and `music-film.json`                      | Archived source identity, provider provenance, prepared soundtrack and measured accents                 |
| `tools/lia-motion/src/Root.tsx`                                                 | Registered active and explicitly named historical compositions                                          |
| `tools/lia-motion/scripts/verify-presentation-geometry.mjs`                     | Independent DOM measurements from rendered frames                                                       |
| `tools/lia-motion/scripts/package-media.mjs` and `verify-delivery.mjs`          | Immutable delivery assets, application schemas and encoded-media measurements                           |

The complete film, shorter landing edit and individual feature focuses have
different editorial roles. The feature inventory is a coverage contract, not a
claim that every assigned capability has been demonstrated end to end. The
coverage report identifies settings-only illustrations, experimental options,
configured integrations and missing visual evidence. Historical compositions
remain distinguishable from the active revision.

Application screens retain their original layout and status colors. Outside
an explicit element focus, their position, scale and internal state remain
stationary. A focus crops the same native source at declared fixed bounds; it
does not redraw a few rows with different spacing. BIP acts outside these
screens. Editorial typography uses the standard blue/violet LIA palette.

## Prerequisites and local authoring

Use Node 24 or later, FFmpeg/ffprobe on PATH and the API Python environment with
NumPy. Install pinned dependencies with the task; do not update dependencies
implicitly while revising a film.

```powershell
task motion:install
task motion:audio
task motion:check
task motion:studio
```

The studio opens on port 3100. `motion:audio` prepares the archived active
recording and its beat map; it does not generate new paid music. Keep original
recordings, credential-free generation requests, provenance and provider terms.
The BPM requested in a music prompt does not replace measured audio accents.
The prepared PCM format does not increase the fidelity of the original source.

## Update a use case or feature

1. Inspect the current application path and its native labels, controls, states,
   colors and responsive geometry. Reference the authoritative component or
   capture in the screen metadata. Use fictitious identities and scenario data.
2. Write the user's intent, useful context, decisive interaction and observable
   result in the chapter and corresponding focus. Prefer landing wording,
   informal address and specific benefits. Keep Story/Why/How independent of
   individual release incidents.
3. Update the faithful view and its provenance. Preserve fixed geometry. Add a
   focus only where it clarifies a particular native element. Keep the complete
   source view mounted and held; do not introduce decorative camera movement.
4. Update canonical feature ownership only when the public inventory changes;
   use editorial topics for additional presentations of existing features.
   Maintain explicit availability and coverage qualifications.
5. Choose an active revision and rebuild source reports. Changing the revision
   requires rebuilding every active delivery; selective packaging cannot mix
   revisions. A source-only report never qualifies an older exported video.

## Review, render and measure

```powershell
task motion:check
node --experimental-strip-types tools/lia-motion/scripts/verify-presentation-geometry.mjs all
node --experimental-strip-types tools/lia-motion/scripts/review-presentation.mjs all
task motion:render -- all
task motion:render -- focus
task motion:render -- master25
task motion:package -- main
task motion:package -- focus
task motion:verify -- all
task motion:preview
```

Geometry review samples rendered DOM bounds before, during and after native
focuses at both working frame rates. Inspect generated stills for text fit,
contrast, hierarchy, source cropping, mascot occlusion and mobile readability.
Watch the complete film and relevant focuses with sound to review transitions,
rhythm, gaze, musical fatigue and synchronization. Unit tests and stills do not
replace continuous playback review.

For a same-revision change, rebuild a specific edit or named focus:

```powershell
task motion:render -- full
task motion:render -- focus focus-mobile focus-avatars
task motion:package -- focus focus-mobile focus-avatars
```

The first main packaging needs both `full.mp4` and `landing.mp4`; later partial
packaging preserves other same-revision verified assets. Serialize packaging
writers. Independent render jobs use separate bundles, but prepare shared
native resources before starting parallel exports. Bound `MOTION_CONCURRENCY`
to available memory and CPU. No render invokes a LIA account or provider.

The main playlist retains the two historical public films declared in
`tools/lia-motion/scripts/preserved-playlist.json`: their original renditions,
credits, AI disclosure and beat maps follow the new teaser and complete film.
The dedicated `presentation` still names only the complete LIA film. Copy every
pinned historical asset into the delivery directory before main packaging;
missing or changed bytes fail instead of silently dropping an older film.
The recorded legacy name prefixes identify the original source, rather than each
rendition's content, so the separate full SHA-256 fingerprints are authoritative.
After an existing main delivery, `task motion:package -- playlist` regenerates
only the manifest, with no render or audio conversion. Main delivery verification
checks the complete ordered playlist and all preserved assets with native schemas;
legacy codecs and original audio are retained without imposing the V6 soundtrack.

The export directory is `exports/lia-motion/` and is ignored by Git. Web delivery
contains hash-named H.264 HD/mobile renditions, posters, beat maps and manifests.
Verification checks actual checksums, native schemas, duration, frame rate,
stream formats, Rec.709 metadata, bounded beats and encoded audio loudness.
Web and master acceptance limits are executable in `verify-delivery.mjs`.
The working master uses ProRes HQ, 25 fps, 10-bit 4:2:2 and stereo PCM 24-bit
48 kHz. Match a broadcaster's requested container and technical specification
before delivery; local technical measurements alone are not broadcast acceptance.

## Public presentation and publication

[ADR-330](../architecture/ADR-330-Landing-Media-Served-Without-Runtime-Work.md)
defines operator-hosted static media. `LANDING_MEDIA_BASE_URL` is a runtime
setting. `/api/landing-media` validates server-side media metadata and returns
safe URLs. The optional manifest `presentation` descriptor explicitly names
the complete film; old manifests still work but cannot provide that CTA's film
without this descriptor. Playlist order is not used to guess the presentation.

The blue Presentation button precedes the guided demo CTA. It lazy-loads a
fullscreen accessible dialog with native controls and localized loading/error
states. Opening suspends the background player, including audible playback;
closing pauses the dialog media, restores keyboard focus and resumes eligible
background playback. Server metadata is read through the bounded same-origin
public UI transport; authenticated API transport remains distinct. Explicit Retry
refreshes the configured manifest through the fixed no-store public route.
Concurrent reads share one origin request, with a bounded refresh cooldown and
fetch timeout owned by `apps/web/src/lib/landing/media-origin.ts`.

Upload every immutable asset first. Compare remote bytes/checksums, preserve
the previous manifest, then atomically replace the active manifest last.
Verify descriptor resolution, posters, HTTP range playback and the full film
from the public application. Restore the previous manifest for a media rollback;
existing immutable assets can remain cached. Never overwrite a hash-named file
with different bytes. Keep operator credentials outside sources and archives.

A public GitHub Release can serve this static directory. Publish every rendition,
poster and beat map as a release asset with its original bare file name, then
upload `manifest.json` last. Configure `LANDING_MEDIA_BASE_URL` to that release's
versioned `/releases/download/<tag>` directory after byte and range checks pass.
The README's stable film and source-archive aliases must contain the same bytes
as the qualified delivery and checked source ZIP. A private repository or an
unpublished release cannot serve anonymous visitors. Keep the full production
master separately when the host's asset-size limit prevents a single-file upload.
When changing the media host, update the deployment's public privacy information
in all six languages to describe direct browser requests to that host.

The film currently has French editorial copy. CTA, dialog and disclosure text
are localized in six languages; the shared video is not automatically translated.
An additional language requires its own reviewed composition and media delivery.

## Preservation and cleanup

Run `task motion:archive` after final source reports and delivered measurements.
The checked ZIP preserves editable construction, locked dependencies, native
resources, captures, provenance, original music and available qualification
receipts. `PRODUCTION-SNAPSHOT.json` names the base Git revision and hashes every
member. Restore the archive onto that checkout at the recorded repository paths.

Retain the active delivery, checked archive and review receipts before removing
superseded builds or exports. Keep musical originals and applicable licenses;
derived PCM, copied application assets, caches and installed dependencies can
be rebuilt. Cleanup must enumerate and validate targets inside the production
workspace and preserve unrelated files. Link the complete published film and
source archive from README/release assets. The archived delivery does not contain
application credentials, real account data or deployment secrets.

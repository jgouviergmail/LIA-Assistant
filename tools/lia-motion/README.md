# LIA motion production

The active editable construction lives in `src/presentation-plan.ts`. It
provides a complete French film, a shorter landing edit and independent feature
focuses. Native application views are recreated from current source contracts
and reference captures with fictitious data. BIP acts outside the application
screens; the complete selectable avatar catalogue has its own sequence.

Read the [production and evolution procedure](../../docs/technical/MOTION_DESIGN.md)
and [ADR-341](../../docs/architecture/ADR-341-Editable-Motion-Production-And-Exclusive-Presentation.md)
for source ownership, review, publication and preservation. The
[coverage ledger](coverage-v4.md) distinguishes assigned feature keys from
visually demonstrated capabilities. Historical filenames are retained for
compatibility; report generations come from `PRESENTATION_REVISION`.

## Author and check

From the repository root:

```powershell
task motion:install
task motion:audio
task motion:check
task motion:studio
```

Use Node 24 or later, FFmpeg/ffprobe and the API Python environment with NumPy.
The studio runs on port 3100. Select `LIA-Full`, `LIA-Landing` or `LIA-focus-*`.
The authoring dependencies remain outside the deployed frontend and Docker
application build context. Pinned dependencies are installed by `npm ci`.

Keep complete source screens stationary unless a declared native-element focus
clarifies the scenario. Focus crops have fixed geometry and preserve native
rows, spacing and context. Editorial typography uses LIA blue/violet; native
status colors retain their meaning. All depicted application data are fictitious.

```powershell
node --experimental-strip-types tools/lia-motion/scripts/verify-presentation-geometry.mjs all
node --experimental-strip-types tools/lia-motion/scripts/review-presentation.mjs all
```

The first command measures actual rendered DOM bounds at the working frame
rates. The second produces chapter/focus stills under the active revision's
review directory in `exports/lia-motion/`. Inspect text fit, hierarchy, native
crops, mascot occlusion and mobile readability. Continuous playback with sound
remains a separate review. Generated source reports are not video qualification.

## Render and deliver

```powershell
task motion:render -- all
task motion:render -- focus
task motion:render -- master25
task motion:package -- main
task motion:package -- focus
task motion:verify -- all
task motion:preview
task motion:archive
```

The ignored export directory contains raw `full.mp4`, `landing.mp4` and
`focus-*.mp4`; packaging creates immutable hash-named HD/mobile web files,
posters, beat maps and native manifests. Verification measures the delivered
bytes, encoded stream properties and audio. The working master is ProRes HQ,
25 fps, Rec.709, 10-bit 4:2:2 and stereo PCM 24-bit/48 kHz. A broadcaster's
technical acceptance specification is separate from these local measurements.

A same-revision update can selectively render/package named focuses:

```powershell
task motion:render -- focus focus-mobile focus-avatars
task motion:package -- focus focus-mobile focus-avatars
```

A new revision requires all active deliveries to be regenerated. Serialize
packaging writers. Parallel render jobs use independent bundles; finish shared
asset preparation first and bound `MOTION_CONCURRENCY` to available resources.
No render contacts a real LIA account or provider.

The local review player requires the active main delivery and includes only
same-revision focuses. Serve `exports/lia-motion/` over HTTP and open
`presentation-review.html`. The historical review URLs lead to the same current
player. Continuous playback review, technical measurements and acceptance by a
broadcaster are distinct receipts.

## Public playback

Use the operator-hosted contract of
[ADR-330](../../docs/architecture/ADR-330-Landing-Media-Served-Without-Runtime-Work.md)
and the runtime `LANDING_MEDIA_BASE_URL`. Upload immutable assets first and
atomically replace the manifest last. The optional `presentation` descriptor
explicitly selects the full film for the blue fullscreen Presentation CTA.
The dialog suspends the background player, including its sound, and restores
eligible playback/focus when closed. Public UI reads are bounded and abortable.
The current film is French; six localized UI labels do not translate its media.

## Music and provenance

The active recording is **LIA — ElectroFunk**, the third commissioned take
created using Google Lyria 3.5. `src/music-v5.json` names the archived MP3;
`src/music-film.json` records prepared PCM and measured musical accents.
`motion:audio` reuses the archived original without paid generation or looping.
The prompt's requested BPM is distinct from measured beat timing. Converting
an MP3 to working PCM does not improve its original fidelity.

Preserve recordings, credential-free requests, generation receipts and terms
under `public/audio/v5/`. Applicable terms are documented in
[the music provenance](public/audio/v5/LICENSE.md); no exclusive copyright or
Creative Commons license is inferred for the generated recording. Remotion's
applicable license is retained in [licenses](licenses/Remotion-LICENSE.md).
Earlier takes and historical soundtrack licenses describe their own recordings.

## Preserve and evolve

The checked source ZIP is an overlay for the base Git revision recorded in
`PRODUCTION-SNAPSHOT.json`. It preserves source paths, locked dependencies,
reference captures, native resources, original music, provenance and available
qualification receipts, with member hashes. Secrets, accounts, installed
dependencies and caches are excluded.

Inspect the actual product before changing an illustrated feature. Update its
chapter/focus, native view, source evidence and coverage qualification together.
Run checks, DOM measurements, still/continuous review, rerender, package and
verify; only then publish and renew the archive. Retain the active delivery and
checked archive before deleting superseded builds. Historical `LIA-Legacy*`,
`LIA-Proof30` and `LIA-Story24` compositions remain named separately from the
current presentation.

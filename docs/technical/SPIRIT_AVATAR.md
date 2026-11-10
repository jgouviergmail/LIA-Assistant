# LIA Spirit avatar

The expressive avatars share one native facial rig and a selectable visual
identity. Settings → Eye style chooses the floating companion and assistant
message portraits; a message retains the mood of its saved Psyche snapshot
when the current style or gender changes. All surfaces share the existing
masculine/feminine preference through
[`useLiaGender`](../../apps/web/src/hooks/useLiaGender.ts). The first render
stays fixed before hydration, then the stored preference updates mounted consumers.

## Catalogue and original offline artwork

The current companion bodies are reviewed, original images authored with the
image-generation tool, not downloaded character meshes. Their eyes, eyebrows
and mouth are supplied by the application, so the offline art never substitutes
for the live face. The [packaging tool](../../scripts/assets/package_companion_art.mjs)
uses offline FFmpeg to encode the approved transparent source images and records
source/prompt hashes, delivery hashes and measured bytes in each manifest.
Encoding does not paint facial organs, remove backgrounds or synthesize motion.
The application has no image-generation or FFmpeg dependency.

The [companion catalogue](../../apps/web/src/components/spirit/companion-catalogue.ts)
owns character IDs, body versions and native face styles. Each body resolves to
`/avatars/{character}/v{version}/{female|male}/body.webp`. Publish a new version
for replacement artwork rather than changing a cached delivery URL. The
original ocular textures remain under the Spirit organ URLs independently of
the current body version.

| Character  | Registry ID | Visual identity                         |
| ---------- | ----------- | --------------------------------------- |
| LIA Spirit | `spirit`    | Opalescent companion                    |
| Mousse     | `moss`      | Botanical spirit                        |
| Lumo       | `lumen`     | Warm luminous spirit with a lunar crest |
| Nimbo      | `nimbo`     | Soft cloud companion                    |
| Orbit      | `orbit`     | Curious cosmic spirit                   |
| Bip        | `bip`       | Compact robot with round luminous eyes  |
| Boulon     | `boulon`    | Rounded mechanical companion            |
| Oscar      | `oscar`     | Miniature butler                        |

Each character has distinct reviewed masculine and feminine bodies; the feminine
art places its pink tied ribbon on the crown. The same native eye textures and
facial channels preserve expressions in both variants. The
[delivery guard](../../apps/web/src/components/spirit/__tests__/companion-assets.test.ts)
checks the actual bodies, manifest hashes, transparency declarations and
bounded still-only payload. Intermediate sources stay outside public assets.

The original Spirit artwork also has a procedural offline authoring path.
Its reproducible model, materials, facial poses and studio are authored in
[`render_spirit_avatar.py`](../../scripts/assets/render_spirit_avatar.py) and
its [`character`](../../scripts/assets/spirit/character.py),
[`geometry`](../../scripts/assets/spirit/geometry.py),
[`materials`](../../scripts/assets/spirit/materials.py),
[`animation`](../../scripts/assets/spirit/animation.py),
[`staging`](../../scripts/assets/spirit/staging.py) and
[`organ_staging`](../../scripts/assets/spirit/organ_staging.py) modules.
This delivery was authored with portable Blender 4.5.4, an offline tool outside
the web/API containers.
Legacy Spirit portrait playback needs no WebGL renderer. Neither playback nor
the live companions require runtime Blender, a provider API or an LLM call.

[`SpiritAvatar`](../../apps/web/src/components/spirit/SpiritAvatar.tsx) remains a
compatible standalone API for transparent, compact WebP clips. The
[catalogue](../../apps/web/src/components/spirit/catalogue.ts) maps the shared
expression vocabulary to
`/avatars/spirit/v1/compact/{female|male}/{expression}[-still].webp`.
Its shared [`playback`](../../apps/web/src/components/spirit/playback.ts)
controller observes document visibility, reduced motion and intersection.
Suspension replaces the animated source with a still; CSS hiding alone would
retain animation decoding. Missing images fall back to the expression still,
then neutral still, then the fixed LIA label, without retrying failed URLs.

The currently selected companion is a hybrid renderer declared in
[`eye-styles`](../../apps/web/src/components/eyes/eye-styles.ts), dispatched by
[`EyesFace`](../../apps/web/src/components/eyes/EyesFace.tsx) into
[`SpiritCompanion`](../../apps/web/src/components/spirit/SpiritCompanion.tsx).
The approved offline body is the fixed fallback inside the native head. Transparent
textures preserve the original sclera, indigo iris, pupil and catchlights;
there is no animated WebP on this surface. Current body URLs come from the
catalogue; original organ textures remain at
`/avatars/spirit/v1/{female|male}/{eye|eye-right|iris}.webp`.
Stationary iris masks use `sclera-mask.webp` and `sclera-mask-right.webp`,
rendered with the original eyelid/lash geometry as holdouts. The moving iris
therefore stays inside the visible sclera and cannot paint over its rim.

The actual [`ExpressiveEyes`](../../apps/web/src/components/eyes/ExpressiveEyes.tsx)
facial layers and [`useEyesRig`](../../apps/web/src/components/eyes/useEyesRig.ts)
drive gaze, blink tapes, mouth/brow contours, idle gestures, mimics, sketches,
response emphasis, emotes and accessories. The hybrid explicitly composes a
real native skin; it has no dummy geometry in the native pose tables.
The rig remains the single facial motion owner and suspends its shared frame
subscription outside the viewport or hidden document. Reduced motion snaps to
the current facial pose and retains the original limb pose. Preview cards use
the local `motionEnabled` gate, then wake
only on hover or keyboard focus; `life=false` alone would still permit breathing.
New device preferences select `bip` at the largest preset; existing saved
styles and sizes are preserved. The public landing explicitly presents the
masculine BIP at that size without changing the application's preferences.
An operator can separately opt one deployment into a BIP introduction campaign
using the server-only runtime `AVATAR_STYLE_ROLLOUT_ID` option, empty by default.
The authenticated host reads `/api/runtime-ui`, rehydrates browser preferences,
and changes only the style and persisted campaign marker once for that identifier.
Later manual choices, visibility, size and both positions remain intact.
The campaign is per browser origin, not per database account, and applies on
the next authenticated visit; it cannot update an offline browser.
Web Locks serialize first application across tabs when supported; storage events
follow later choices without writing back. Without Web Locks, a latest-record
re-read protects delayed replies but is not a cross-process transaction.
Clearing the option stops new applications without restoring old choices.
Use a stable unique identifier for each intentional campaign; never reuse an old
identifier or rotate it automatically for every release. Ordinary installations
leave the option empty. See [ADR-342](../architecture/ADR-342-Opt-In-Runtime-Avatar-Preference-Campaigns.md)
for lifecycle, compatibility and qualification limits.
The client-only [application host](../../apps/web/src/components/eyes/ApplicationEyes.tsx)
mounts once under the authenticated dashboard layout, retaining the same
face across its pages. Chat phases travel through an ephemeral
[scalar store](../../apps/web/src/stores/eyesChatStore.ts); Live and TTS retain
their existing playback owners. Outside chat, the notification shortcut
keeps its existing subscription and background-run polling, while the
animated face reflects that work. Route changes release chat-owned signals
without clearing current audio playback or the held response tone.

Spirit paints the same native reactions with travel bounded to its head.
The body registration retains the approved visible dimensions. A body-alpha
mask contains the fixed face; the live volume projects that boundary along
with the eyes and mouth. Eyebrows and emotes can remain outside the face mask.
Squints and blinks cover the intact ocular
textures rather than vertically crushing the iris and its reflections.
The feminine sculpt wears an original [satin hair ribbon](../../scripts/assets/spirit/ribbon.py),
baked into both the companion body and compact portraits under the same head
transform. It uses the existing playback and rig without another runtime layer.
Eye and mouth travel share the same bounded facial displacement under the
moving head; the pupils retain independent saccades. Subtle body-only lighting
reads the existing head channels without adding another animation clock.

Oscar's human face uses fixed eye sockets instead of the creatures' elastic
facial travel. Both ocular patches follow one rigid cranial frame at their
authored anchors; the cheek relief never stretches one globe independently.
Iris aim, eyelid closure, blinking and brows remain native reactions. Saccade
stretch does not move the sockets, and facial droplets stay attached beside
them. Jaw motion keeps its own projected articulation.

The original offline authoring sources also include **Mousse** (`moss`), a mint botanical
spirit with folded leaves, and **Lumo** (`lumen`), a warm luminous spirit with
a crescent-shaped crest. Their original silhouettes, geometry and materials are
procedural offline sculpts. The design research considered the soft proportions
in [Meta's Muse presentation](https://introducing.muse.ai/) and the variety of
spirits in the [Nichibunken folklore archive](https://shinku.nichibun.ac.jp/esoshi/theme.php?disp=EN).
No reference image, branded character mesh or animation is shipped.
Their [renderer](../../scripts/assets/render_companion_characters.py),
[Mousse](../../scripts/assets/spirit/moss.py),
[Lumo](../../scripts/assets/spirit/lumen.py),
[anatomy](../../scripts/assets/spirit/companion_sculpt.py) and
[materials](../../scripts/assets/spirit/companion_materials.py), with a
[dedicated studio](../../scripts/assets/spirit/companion_staging.py), keep
that artwork reproducible independently of the application.

Their feminine sculpts have a slimmer pear-shaped body and a small pink
[tied ribbon](../../scripts/assets/spirit/companion_ribbon.py). Masculine
sculpts have broader shoulders, a stockier body and a lower crest. The
shared facial anchors retain the same native reactions in both variants.

The original ocular layers and native facial rig are shared. Eye style cards
show both genders for every hybrid character; the chosen assistant gender
still selects the floating companion's variant. Hover/focus alone wakes the
card previews. Selecting a new character retains the existing size, visibility
and position preferences and introduces no clip decoding or motion clock.

[`SelectedCompanionPortrait`](../../apps/web/src/components/psyche/SelectedCompanionPortrait.tsx)
uses this same catalogue and [`EyesFace`](../../apps/web/src/components/eyes/EyesFace.tsx)
for every selected style, including Spirit. Historical messages use
`staticPose=true`, `life=false` and no live rig subscriptions or canvas. The
shared playback gate enables a native live pose only for an eligible visible
portrait; a hovered history row keeps its saved expression. Leaving the
viewport, hiding the document or reduced motion returns the frozen pose.
The legacy compact Spirit clips are not the selected-message rendering path.

Hybrid mouths and eyebrows use the native sculpted contours; Bip retains its
digital mouth on the emissive visor. A body-alpha boundary contains moving eyes
and mouth, while eyebrows remain in a sibling layer. Curved teeth and tongue
are clipped by the current cavity rather than a fixed rectangle. The facial
writer refreshes newly added anatomy when the mouth projection changes, so a
live Bip-to-Oscar switch keeps the same rig and still animates its teeth.
Character identity travels separately from the shared native skin through
[`acting-profile`](../../apps/web/src/components/eyes/rig/acting-profile.ts).
Its calibrated resting target is shared by frozen and live poses; a change of
identity does not allocate another clock or replay an archived performance.

The other native eye skins appear in an original procedural toon monitor through
[`MonitorCompanion`](../../apps/web/src/components/eyes/MonitorCompanion.tsx).
The static body is authored by
[`render_companion_monitor.py`](../../scripts/assets/render_companion_monitor.py)
and [`monitor`](../../scripts/assets/spirit/monitor.py). Its screen projection
comes from the shipped manifest. A stationary rounded screen boundary clips
the eye graphics and mouth; eyebrows remain in a separate layer. The monitor
retains the same native rig, with a decorative phosphor display paused by the
rig's viewport/document visibility marker, local preview gate and reduced motion.

## Shared facial anatomy and catalogue preferences

The companion [mouth contours](../../apps/web/src/components/eyes/rig/sculpted-mouth.ts)
project the native signed smile and jaw channels into a continuous cavity,
curved teeth and tongue. The current cavity clips the inner anatomy, then the
body mask contains the complete face. BIP and the monitor skins retain their
digital mouth projection. The sculpted eye artwork keeps its proportions;
expression lids and blinks cover it through the same native rig.

Smiley was retired at the owner's request. It is no longer offered or rendered.
Previously stored selections resolve through the validated style-preference
reader to the current default without resetting size, position or visibility.
Its dedicated sphere implementation and assets are removed; shared facial
anatomy remains available to the companions. Chat mood emoji are a separate
surface and are unchanged.

The existing [`useEyesBehavior`](../../apps/web/src/components/eyes/useEyesBehavior.ts)
selects the companion's expression and reactions. Its `speaking` state comes
from existing audio playback; the procedural mouth is expressive speech motion,
not phoneme synchronization or additional TTS. Comments, Live and Live direct
use the same speaking pose. Live output keeps priority over delayed input captions
and tool progress until playback stops; an interruption, standby or session end
releases it. A WebRTC speaking hint received before the remote track is kept for
local playback, while a captured or Simli-routed output follows actual playout.
See the separate
[speaking avatar integration](SPEAKING_AVATAR.md) for provider video.

Display geometry is owned by
[`AssistantAvatar`](../../apps/web/src/components/psyche/AssistantAvatar.tsx) and
[`eyes.css`](../../apps/web/src/styles/eyes.css) and the
[size presets](../../apps/web/src/stores/eyesWidgetStore.ts). Frozen message
portraits use the same native geometry in their compact frame; companion
presets share the renderer at their own display size. The drawing buffer
remains independently bounded by its geometry module. Download size,
decoded memory and real-device smoothness must be measured on the actual delivery.

## Native anatomical volume and layout

[ADR-340](../architecture/ADR-340-Native-Avatar-Volume-From-Reviewed-Offline-Art.md)
records the geometry, native motion ownership and fallback boundaries of this surface.
The [native volume guide](NATIVE_AVATAR_VOLUME.md) maps the alpha material,
projected face, resource lifecycle and approximation limits to their sources.

The hybrid characters and monitor use
[`BodyVolume`](../../apps/web/src/components/eyes/volume/BodyVolume.tsx) when
their native motion gate permits it. The approved body image textures a closed
mesh whose relief is described by
[`volume-geometry`](../../apps/web/src/components/eyes/volume/volume-geometry.ts).
It has actual front/back depth and tangent facial anchors rather than a rotated
flat bitmap. Hidden anatomy is an approximation of the reviewed frontal art;
this does not supply independently authored views of an original full sculpt.
There is no external 3D engine or downloaded character mesh.

The source's complete alpha coverage remains in a thin, depth-tested material
behind the relief. This preserves fine hair and silhouette details that the
physical mesh approximates. Side materials are identified at their vertices;
interpolating front and back normals cannot create an opaque fringe.

The existing rig also articulates the drawn appendages through
[`limb acting`](../../apps/web/src/components/eyes/rig/limbs.ts) and
source-specific [joint profiles](../../apps/web/src/components/eyes/volume/limb-profiles.ts).
Spirit and Nimbo use their lateral appendages; Mousse and Lumo use arms and
feet; BIP, Boulon and Oscar use arms, wrists, legs and feet. Orbit's ring stays
rigid, and the monitor and eye-only styles gain no limbs. Both variants
retain their own anatomical profiles and the same native motion owner.

Quiet settling, occasional facial-life beats, attentive opening, one-sided
thoughts and phrase-aligned speech gestures use the existing springs and clock.
Body scenes share authored preparation, action and recovery phases across body,
face and joints; wrists trail the gesture and the material bounds deformation.
Registered support points ground stage scale/roll before viewport containment;
interruptions release continuously. Quiet arms follow breathing, while planted
feet remain still between purposeful stance changes.
The current repertoire retires full spins, somersaults and the repetitive jig.
Breathing and purposeful reactions remain, with a single jump and landing,
an upright floating hold, and a readable bow. Random head rocking and eye
hops are absent; acknowledgement and thoughtful inclination are explicit
conversation cues. The [finishing specification](../superpowers/specs/2026-11-08-avatar-finishing.md)
and its linked implementation plan describe this bounded refinement.
The physical surface and fine alpha fringe share prepared source-space weights,
and the shader transforms normals with the deformation's spatial Jacobian.
This preserves the original textures without inventing fingers or texture detail.
Turned surfaces receive a bounded material-specific light response while the
neutral artwork stays unchanged. Cold scarves keep the fitted band and upper
knot attached; only their free end trails real lateral movement and settles
at rest. The [native volume guide](NATIVE_AVATAR_VOLUME.md#local-limb-articulation)
owns the rendering contracts and links their behavioral and anatomical tests.

The existing rig's writer drives
[`volume-writer`](../../apps/web/src/components/eyes/volume/volume-writer.ts)
with the same head and facial channels. Eyes, eyebrows and mouth retain their
actual native contours on projected surface wrappers. The monitor projects
its complete screen and separate brow layer together, retaining the rounded
screen clip. The live hybrid face clip follows the projected body contour;
its stationary iris masks still contain independent pupil travel.
[`physical-prop-writer`](../../apps/web/src/components/eyes/volume/physical-prop-writer.ts)
projects the worn freezing laurel and temple/eye drops on the same surface.
Floating environmental motifs retain their
own stage anchors. Layout landmarks calibrate each character and variant.

[`volume-binding`](../../apps/web/src/components/eyes/volume/volume-binding.ts)
receives viewport, document and reduced-motion state from the native rig owner.
It adds no independent observer or animation clock. Stopped previews and
historical portraits have no canvas. A hidden or reduced-motion body uses its
fixed bake; unavailable WebGL, failed texture loading or context loss also
retain that fallback. Unmounting or replacing size/identity releases the old
graphics resources. Layout-time binding resets readiness before a replacement
canvas can suppress its fallback. The framing and independently bounded drawing
buffer are owned by the renderer sources, not the displayed size preference.
Joint angles participate in redraw invalidation, so independent limb motion
reaches the GPU even when head pose and lighting stay unchanged. The same
visibility, reduced-motion and context-loss gates stop that drawing work.

[`layout-profiles`](../../apps/web/src/components/eyes/layout-profiles.ts)
publishes static landmarks for each complete avatar and gender. Crown and face
landmarks position emotes and contextual props; the eye span follows the skin's
actual width and spacing. Neck position and scarf width come from the same
collar geometry used by the live surface, avoiding separate fallback measurements.
The shared scarf fit independently maps band thickness and tail length, including
the CSS material used when graphics are unavailable. BIP, Oscar and Nimbo have
closed collars with lateral returns; prepared facets feed the GPU and fallback.
Their band follows the body while the free knot/end sways on the existing clock.
The fallback composites each projected front/rear group before applying the
weather fade, preserving continuous textile edges. Its two stages sit beside the
head, with explicit rear/head/front order and the same head origin and motion;
each facet composes its source basis and head projection before the opacity
boundary, retaining source depth across browser compositors. When cold cloth is loading
or unavailable, the whole avatar keeps that coherent fallback until all required
live layers are ready; warming can immediately reuse its prepared live body.
Bare `ExpressiveEyes` consumers retain their existing layout and screen tokens.
These landmarks add no state subscription or frame work.

## Offline context props

[`AmbientAccessories`](../../apps/web/src/components/eyes/AmbientAccessories.tsx)
declares decorative material slots for rain, storm, cold, freezing, snow, hot,
heat, fog, wind and night. The original transparent local stills live under
`/avatars/context/v1/{weather}.webp`; their manifest records width, height,
bytes and SHA-256 for each prop plus the pack total. The
[real-file guard](../../apps/web/src/components/eyes/__tests__/context-assets.test.ts)
checks exact inventory, dimensions, WebP alpha declarations, hashes and delivery
budgets against the actual files, including the wider scarf canvas.

The current cold scarf has its own versioned delivery under
`/avatars/scarf/v1/`. Its transparent `front.webp` supplies the native garments
and their fitted fallback. `knit.webp` remains an offline
authoring material; the live surface does not request it. The old context pack
remains immutable.
[`cloth-geometry`](../../apps/web/src/components/eyes/volume/cloth-geometry.ts)
places the band, knot and hanging end at the character's calibrated attachment,
following its head pose in the same graphics context. Closed collars on BIP,
Oscar and Nimbo pass behind the body; other front patches are composited ahead
of its coarse subdivisions. Without usable graphics the shared fitted fallback
remains. The
[scarf guard](../../apps/web/src/components/eyes/__tests__/scarf-assets.test.ts)
checks both actual textures, manifest hashes, alpha declarations and pack budget.

There are no eager `img` sources or inline background URLs. The stylesheet
installs a bitmap only when its name appears in `data-weather-props`, which the
native writer derives from the context channels. Snow shares one still across
edge slots `a`, `b` and `c` under a single native fall wrapper; the face centre
remains free. Fan, sweat and snow motion use the existing ambient channels,
not timers or a second frame loop. These slots are decorative, ignore pointer
input and are omitted when `life=false`, including historical portraits.
The cold fallback uses the calibrated garment declaration until all required
live layers are ready; the live material is not a second canvas or clock.

The props consume the existing
[`companion environment`](../../apps/web/src/components/eyes/useCompanionEnvironment.ts)
snapshot. Its
[`condition derivation`](../../apps/web/src/components/eyes/environment.ts)
keeps independent current condition, wind and temperature flags. A cold rainy
night can therefore retain its scarf, rain prop and night accessory together;
freezing adds frost while keeping the cold condition, and extreme heat adds
sweat while keeping the fan. Day phase follows the account's civil clock and
is independent of the weather observation. The legacy dominant weather remains
available without reducing the accessory set to one choice.

The
[`live context adapter`](../../apps/web/src/components/eyes/rig/live-context.ts)
forwards canonical readonly flags to the native rig. Thinking, work, sleep,
speech and other expressions keep valid contextual props instead of retiring
them to reserve the conversational stage. Expressions and mouth motion still
have their own native channels. Viewport/document suspension and reduced motion
pause movement; display opt-out and owner cleanup remain effective.

Only a current observation supplies weather flags. The environment owner reuses
its existing timer for observation and expiry boundaries and its ordinary
refresh deadline; no boundary triggers an extra provider request. Expiry removes
weather while retaining the valid account timezone. A failed refresh or malformed
payload retains cached evidence only until its original expiry; a valid response
with explicitly absent weather clears it. Account/owner cleanup forgets the
ephemeral snapshot. These props add no weather provider request, LLM call or
independent animation clock. Raster artwork and its encoding remain offline
authoring steps; they are never generated while the assistant runs.

## Regenerate offline

For the current companion bodies, prepare reviewed transparent images and an
authoring JSON array containing `character`, `variant`, `version`, `source` and
the exact `prompt`. Use the existing offline Node/FFmpeg tools and a temporary
output directory:

```powershell
node scripts/assets/package_companion_art.mjs .tmp/companion-art/inputs.json .tmp/companion-art/delivery
```

Inspect the produced gendered bodies, provenance and manifests before copying
the reviewed version directories into public assets and updating the catalogue.
The packaging helper and real-file guard own the enforced budgets. Keep source
images, prompts and intermediate encodings outside the shipped application.
Context props follow the same reviewed-image and offline WebP delivery principle;
their manifest and guard own the non-square canvas and per-prop dimensions.

The procedural sources below remain available for the original Spirit ocular
layers, legacy portrait clips and the monitor.
Use an existing portable Blender executable; these commands do not install one.
Run from the repository root. Begin with one bounded expression before omitting
`--expressions` to render the complete vocabulary:

```powershell
$blenderExe = 'D:\path\to\blender.exe'
& $blenderExe --background --factory-startup --threads 2 --python scripts/assets/render_spirit_avatar.py -- --output .tmp/spirit-avatar/frames --variant both --expressions neutral --frames 40 --size 192 --engine BLENDER_EEVEE_NEXT --samples 48
```

The example authors the requested frames over the choreography's loop. The encoder
uses `LOOP_SECONDS` to derive timing. Compact delivery samples fewer frames,
including fast blinks, with variable durations preserving that loop.
Inspect the generated manifest when changing the recipe or `--frame-ms` override.
Full-resolution intermediate clips are not shipped when no production consumer
uses them. Samples and CPU thread limits bound work, not render duration.

Render the static companion body and original eye layers before encoding:

```powershell
& $blenderExe --background --factory-startup --threads 2 --python scripts/assets/render_spirit_avatar.py -- --output .tmp/spirit-avatar/frames --variant both --body-only --size 192 --engine BLENDER_EEVEE_NEXT --samples 48
& $blenderExe --background --factory-startup --threads 2 --python scripts/assets/render_spirit_avatar.py -- --output .tmp/spirit-avatar/frames --variant both --organs-only --samples 48
python scripts/assets/encode_spirit_avatar.py --input .tmp/spirit-avatar/frames --output apps/web/public/avatars/spirit/v1
```

The encoder records dimensions, timing, measured bytes and hashes in
`manifest.json`; its source owns the enforced size budgets. Intermediate PNGs,
portable binaries and optional `--save-scene` Blender files stay outside shipped
assets. Publish a new version directory and change catalogue/CSS URLs when
replacing cached artwork.

Review silhouette, eye proportions, alpha, blink continuity, loop seams and
actual asset sizes. Source/behavior tests establish motion, fallback and
preference contracts, not visual fidelity or real-device performance.
Documentation checks use the Git index: use `task lint:docs:preview` while new
files are unstaged.

Regenerate the original procedural Mousse and Lumo artwork into a temporary directory with their dedicated
offline renderer. Its `--portraits` flag adds neutral PNG art references for
review; those intermediates stay outside the public application:

```powershell
& $blenderExe --background --factory-startup --threads 2 --python scripts/assets/render_companion_characters.py -- --output .tmp/companion-characters/drafts --character both --variant both --samples 48 --portraits
```

Use these renders as original sculpt references. Current body deliveries use the
reviewed-art packaging workflow above; do not overwrite their cached versions
with legacy procedural renders. The real-file
[delivery guard](../../apps/web/src/components/spirit/__tests__/companion-assets.test.ts)
checks the catalogue's actual body URLs, dimensions, transparency declarations,
hashes and bounded still-only payload.

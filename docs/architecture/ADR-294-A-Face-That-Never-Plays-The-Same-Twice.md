# ADR-294 — A face that never plays the same thing twice: brows on the eye, generated speech, warped beats, scenes that count resting time

**Date**: 2026-09-17
**Status**: Accepted
**Amends**: ADR-264 (living brows and mouth), ADR-252 (the rig), ADR-240 (the widget)

## Context

The owner watched the running avatar and said: the eyes are fluid, the brows
and the mouth are the weak point, the transitions are not smooth, the whole
thing is *predictable* — and "the random scenes, I have never seen them".
Every finding below was MEASURED before anything was changed: on the real
widget in a real Chromium against the dev server (a recorder wrapping
`CSSStyleDeclaration.setProperty` to log every `--rig-*` write, five minutes
on the chat page of a throwaway account, `cozmo` at the large size), in the
rig itself under a simulated clock, and in the owner's own psyche history.

**The scenes were never seen, and the mechanism was fine.** Six sketches in
ten simulated minutes, three in five real minutes on the chat page, one on the
landing 62 s after mount. The owner's resting mood over 541 psyche states was
`determined` 44 %, `energized` 21 %, `neutral` 14 %, `defiant` 11 % — a
resting face of `neutral` or `attentive`, both of which allow a scene, so the
hypothesis "the resting expression excludes them" was refuted. What hid them:

- the wait (45–120 s) was drawn ONCE at rig construction and counted on the
  rig's own clock; every App Router navigation unmounts the widget, and every
  mount started the wait over;
- the wait ran on any expression, so a draw that fell during a thought, a
  reply or a reaction was simply lost and the next pushed a minute or two on —
  and a person looks at the avatar mostly right after a reply, never a minute
  into silence;
- in dev, every file save reloads the page (measured: the landing capture was
  reloaded by an edit under `apps/web/e2e/`);
- the gaze travels 0.14 em per unit — six pixels at the large size — so the
  scenes that lived in the gaze (the fly, the dizzy roll, the groove) read as
  one more idle glance.

**The brows and the mouth were predictable for measurable reasons.** In five
minutes: 27 flashes of the presence "ink" from 0.5 to 1.0, in 30–123 ms each,
visible on the frames as two dim organs switching on — an interface element,
never a face. Every mouth beat reached half its travel at ~50 ms, ninety per
cent at ~100 ms, its peak at 150 ms (one attack spring), held 600–720 ms and
came home on the same `base` 650 ms — a curve the eye learns in a minute; the
full grin came back eleven times, identical. The brow was pinned to the top of
the eye BOX, so a joy dome (the shape squashed to 0.55 around its fifth) left
it floating a third of an eye above; it had one thickness whatever it did, and
no way to knit. Three independent timers (eye beats 1.9–5.6 s, mimics 6–14 s,
scenes) produced a facial event every five to eight seconds with no rhythm —
neither a silence nor a phrase, which is what a tic is. At every expression
change the mouth held its ground for 45–70 ms and the aura for 120 ms, then
left at zero velocity, and the mask blink reopened at 130 ms while the host
swapped the face at 140 — the new eyes were revealed mid-morph. Speech was a
sum of sines: louder, quieter, closed on a slow envelope, and the same phrase
over and over on a long answer.

Owner arbitration (2026-09-17): full presence and a life of its own for EACH
brow (D1, yes); the mouth stays a solid slab — "it fills more, it is more
cartoon" (D2, no crescent); no "replay" button — what matters is visibility
without frequency or repetition (D3); generated speech (D4, yes); everything
delivered, tested and simulated (D5).

## Decision

### 1. A scene waits in RESTING time, on a clock the host keeps

`SketchClock` (`rig/sketches.ts`) counts only the frames the face is actually
resting (a `SKETCH_EXPRESSIONS` state with no scene on), and the rig is handed
one by the host — a module-level clock in `useEyesRig`, one per document,
given to every living face and never to a preview — so a navigation that
unmounts the widget never restarts the wait. A draw that falls during a
thought is not lost: it waits. The first scene of a session waits 20–40 s of
rest (it is what proves there is a character), the later ones 45–120 s. The
last three scenes played are never drawn again right away (`SKETCH_HISTORY`).
And every scene that looks aside turns the HEAD after the eyes on an eased
spring (`HEAD_FOLLOW_X_EM` / `HEAD_FOLLOW_Y_EM` on `massX` / `massY`), so a
scene written in the gaze is a scene and not a glance. Verified on the chat
page after the change: see § Evidence.

### 2. The brow sits ON the eye, has weight, knits, and leads

- **Full presence, no ink.** The `browA` and `mouthA` channels are gone
  (three channels removed; `browX` per eye and `mouthX` added, `browS` per
  eye derived — 59 → 61). The stylesheet draws both organs at `--has-brow` /
  `--has-mouth`, nothing fades in. Every scene, mimic and gesture lost its
  presence tapes.
- **Anchored to the visible edge.** `.lia-eye-brow` takes
  `top: calc(var(--oy) * (1 - var(--sy)) + var(--lid-top) * var(--sy))` — the
  visible top of the shape after its scale around its anchor and its lid —
  and sits above it by its own height. A joy dome brings the brow down with
  it; a widened startled eye pushes it up; a heavy lid lays it on the lid.
  Verified in the browser on the matrix of expressions × styles.
- **Weight, derived.** `browS` is computed every frame from the brow's own
  final height and arch (`browStretchFor`): raised, it thins and lengthens;
  pressed, it thickens and shortens, at constant ink, bounded in
  [0.6, 1.4]. No pose declares it; no beat can forget it; the bubble guard
  reads the same function.
- **Knit.** `browX` in screen em: a scowl, a focus, a worry, a fright and a
  grief pull the pair toward the nose; a startle sends it apart; a thought
  presses one brow in. Declared per pose through the `brow()` helper's sixth
  argument.
- **Its own dynamics group.** `brow` (frequency 1.3 × the pose's, a little
  under-damped, lead 0) — anticipated and exaggerated like the pose, and
  ahead of the eye on every preset: a startle is brows first, pinned by a
  test that measures which reaches ninety per cent of its travel first.
- **Couplings.** The brows follow the gaze and their own lid as before, and
  now the smile: a curve above the resting one lifts them a hair
  (`BROW_SMILE_LIFT_EM`), one-sided, written absolute like every derived term.
- **Each brow its own animation.** A one-sided beat (the `brow` gesture, the
  corner tug, the tilt) is written once and FLIPPED to either side by the
  host (`choreo.flipTapes`: sides swap, screen-signed channels negate); and
  every performance is WARPED per channel (§ 4), so the two brows of one grin
  lift by different amounts at different instants.

### 3. The mouth slides, and it SPEAKS

- `mouthX` slides the whole slab sideways (a thought purses to one side, a
  `hmm` and a `smirk` lean, the chew wanders, the suspicious scene purses
  aside). The slab itself is kept, by the owner's choice.
- **Speech is generated, never looped** (`rig/speech.ts`). A chunk of five
  and a half to ten seconds is keyed the way an animator would key it:
  syllables (an open of 0.22–0.66 for 60–130 ms, a close for 45–95 ms, no two
  alike), words of one to five syllables, gaps of 120–300 ms between words and
  550–1000 ms between phrases every four to nine words, a SHAPE per word
  (width, curve, corners, slide) that relaxes on a phrase pause, and a
  stressed word a third of the time that the brows mark — both, the right one
  trailing and smaller, or the left alone — and the head nods on half of. The
  chunk ends on a pause so a wrap never cuts a word. It is the `speaking`
  state's PATTERN: a pattern that reaches its cycle is now RESOLVED AGAIN
  with the time it ran over rather than rewound (`advanceBeats`), so the
  fixed search table repeats as before and speech comes back as a new chunk.
  The pose under it is a closed, faintly smiling mouth — the listening face
  between two phrases. A rig without entropy speaks from a seeded stream of
  its own, deterministically. The eyes keep their bob as a loop; the mouth
  loops of ADR-264 are gone.

### 4. No two performances alike

- **Warp** (`choreo.warpTapes`): one draw sets the pace of the whole
  performance (0.85–1.15), then every CHANNEL draws its own time jitter
  (± 6 %) and, for a relative tape, its own size (± 12 %) — one factor per
  channel, so a hold and its release stay joined; absolute tapes are paced,
  never resized (a lid at 1 is a fact). Applied to every mimic, every host
  gesture and every scene the rig draws.
- **A release of its own** (`choreo.withRelease`): each mimic appends, per
  relative tape, a release tape — one key at the pose, starting where the
  hold ends, on the scene's own spring (`MIMIC_RELEASE`: a sulk lingers at
  0.9 Hz, a smack snaps back at 3.5 Hz) for as long as that spring settles.
  Found on the way: `tapeSpringIn` imposed a tape's spring BEFORE the tape's
  first key — a release's slow spring was slowing the attack it followed —
  fixed at the runtime (a tape that has not started leads nothing).
- **Phrases, not a cadence** (`life.ts`): a silence of 8–16 s, then a beat
  that continues into a follow-up 1.2–2.5 s later a third of the time, so a
  thought unfolds in one, two or three beats; never the mimic just played.
  And the face ANSWERS the eyes: after a share (30 %) of the idle gestures the
  host cues `rig.answerIn(350–800 ms)`, which brings the next mimic forward
  on a resting face only — a glance followed by a smile, in one thought.

### 5. Transitions

- The organs depart with the eyes: `mouth` group lead 45 → 30 ms, the corner-
  first smile kept at 20/40 ms, the aura at 100 ms (the catch-lights are the
  only aura left).
- **The pose's pull builds up at a hand-over** (`SPRING_BLEND_MS`): when a
  beat hands a channel back, the target jumps and the acceleration used to
  jump with it — the whole pull of the pose in one frame, a kink at the top
  of the motion. The pose spring's frequency now ramps from a tenth of itself
  to the whole over 120 ms; the acceleration starts near zero and grows,
  continuous by construction, measured by the jerk around the hand-over
  against the beat's own. Only hand-overs FROM a beat blend: an attack keeps
  its author's spring, a hold onto a release keeps the release's, and a new
  expression takes its dynamics outright — a startle blended out of a sad
  face would be a startle dulled by the face it interrupts (pinned).
- **The mask blink holds shut past the swap** (`maskBlinkTapes`): the host
  declares the blink a mask (`blinkMask`, `data-blink-mask` on the root) when
  it swaps the face under it, and the rig keeps the lids closed until
  `MASK_APPLY_DELAY_MS + 50` before reopening on the blink spring — the new
  eyes are revealed once they have begun to move, not mid-morph.

## Consequences

- Channels: 61 (`mouthA`, `browA×2` out; `mouthX`, `browX×2`, `browS×2`
  in). The pixel budget of the moving hold (`life.test.ts`) still holds with
  the anchor read through the stylesheet's own arithmetic (`screen.ts`), the
  brow's thickness now a channel of it.
- The bubble guard measures the brow's reach with the anchor and the weight:
  the widened startled eye lifts the edge the brow sits on, so the bubble's
  margin rose from 1.25 to 1.5 of its em (0.9 em of the widget).
- `speaking` is a pattern at full frame rate, as ADR-264 already noted for
  the speech brows; nothing changes in kind.
- The eyes suite went from 515 to 546 tests over 27 files; the full frontend
  suite (660 files, 8 419 tests) and the complexity ratchet (45 functions at
  15 or more, max 53) are unchanged in verdict.

## Evidence

Measured on the chat page of the dev instance (real Chromium, five minutes,
the same recorder, before and after this ADR — a proof account created
through the API and activated in the database):

| | Before | After |
|---|---|---|
| First scene after mount | 107 s | 22 s (the first-scene band, in resting time) |
| Scenes in five minutes | 3 (107, 204, 295 s), none with the head | 3 (22, 125, 248 s), the head following the gaze on each |
| Presence writes (`--rig-brow-a-l`) | 2 230 (27 flashes 0.5 → 1) | 0 (no presence channel) |
| Distinct mouth attack times (t90) | 19 of 41 excursions | 25 of 43 (warped per performance) |
| Mask blink declared on a face swap | never | `data-blink-mask` on every masked change |

The hermetic harness (the real rig and stylesheet, the exact markup, no app)
rendered the matrix of twenty expressions by five brow-bearing styles after
the anchor change, and frozen strips of a grin (brows first, eyes squashed to
arcs, a release that takes 800 → 1 700 ms), of the `brow` gesture flipped to
the left, and of the double take with the head following the gaze.

## Rejected

- **A "replay a scene" button** in the settings (proposed D3). The owner: what
  matters is visibility without frequency or repetition; the resting-time
  clock and the first-scene band deliver that without a control.
- **A tapered crescent mouth** (proposed D2). The owner keeps the solid slab:
  "it fills more, it is more cartoon, there is plenty of expression in it."
- **Blending every spring change.** Blending from a fast attack spring INTO a
  slow pose spring made the kink worse (the target jump dominates), and
  blending a new expression's dynamics out of the previous face dulled a
  startle. The ramp of the pose's own pull, on hand-overs from a beat only,
  is what the jerk measurement accepted.
- **Making the host's idle-gesture cadence bimodal.** The eyes' wander is
  what keeps a resting face alive between beats; a six-second silence of the
  EYES reads as a freeze. The rhythm lives in the face's own life instead,
  and the face answers the eyes.

## Related

ADR-264 (the organs this amends), ADR-252 (the rig, the boundary rule, the
tape mechanism every part of this rides), ADR-253 (the tone accents, which
now flip too), ADR-240 (the widget and the landing mount).

## Amendment — contextual direction and continuous contours (2026-09-21)

The owner's follow-up supersedes the masked-swap and CSS comic-motion choices
above. A solid mouth is retained, but its outline now interpolates through a
fixed SVG topology. The signed curve no longer flips the whole mouth at zero.
Brows have independent cubic contours. The `traits` and `anneaux` eyes also
morph between line, arch and ring instead of selecting a different CSS recipe.
`rig/apply.ts` remains the only DOM writer and suppresses unchanged attributes.
The stylesheet retains material, layout and the decorative emote.

All skins share the same direction. The amber `smiley` mentioned in the original
implementation was subsequently retired by the owner; see the catalogue-retirement
amendment in [ADR-340](ADR-340-Native-Avatar-Volume-From-Reviewed-Offline-Art.md).

1. Psyche's pleasure, arousal, dominance, curiosity and engagement modulate the
   resting pose and spontaneous choices. Disabled Psyche uses neutral values.
2. Actual activity directs attention. Thinking is a held consideration with
   small gaze changes and breathing; it has no chewing or spontaneous mimic.
   Reading, organizing, communicating, calculating, creating and exploring
   have different attention patterns. Unknown capabilities remain generic.
3. The completed answer's register is held, then eased back toward temperament.
   Its duration lives in `expression-engine.ts` and `eyesSignalsStore.ts`.
   Text alone never animates speech; TTS and Live use actual playback state.

Scenes own their channels, except for a spontaneous blink. An activity start
interrupts a scene even when the expression name stays unchanged. The response
hold and release exclude spontaneous scenes. An interruption retains spring
position and velocity. The resting clock survives navigation; its diagnostic
counters distinguish started, completed and interrupted scenes. There is no
product replay button. The first wait uses its shorter band only once.

### Evidence at the execution boundary

`apps/api/src/domains/agents/expressivity/activity.py` defines the versioned
`Activity` contract. The effect gate observes the original coroutine **after**
admission and deduplication, including confirmed draft executors. It never
observes plans, requested calls or results merely served from the ledger.
Nested operations retain one owner; parallel invocations have separate IDs.
Native voice lookups use the same observer and the direct Live HTTP response
carries its terminal evidence. Before that response, the direct voice UI can
show processing but cannot claim a specific tool family has executed.

An event contains only version, run/invocation IDs, family, intent, phase and
outcome. It contains no arguments, tool content, secrets or exception text.
Explicit failure, cancellation, waiting and opaque results never imply success.
Draft preparation is distinct from an accomplished action, even when preparing
the draft succeeded. An emitter failure cannot repeat or prevent execution.
Category resolution uses the existing manifest conventions; no second tool
registry or capability list is introduced.

The frontend validates the wire contract, binds it to the active answer/run,
ignores replay and stale events, bounds retained invocations and expires a
missing terminal without fabricating an outcome. Its bounded activity summary
and the existing tone annotation are archived in message JSONB. No schema
migration is needed. Loading a historical message does not replay its gestures.
React batching of a short answer and its `done` event cannot lose the reaction.
Conversely, a slow synthesis cannot age out its activity before the answer:
completion recalls the same terminal evidence once, and duplicate `done`
events cannot restart its release.

### Cost, lifecycle and verification

No LLM call, prompt instruction, model choice, token allowance or quota path
is added. The existing tone annotation is reused; absent tone uses the existing
local content classifier. These signals never write Psyche or learned memory.
Rendering pauses in hidden tabs, honors dynamic reduced motion, cleans up
subscriptions/timers and preserves the existing persisted style preferences.
Viewport observation also removes offscreen faces from the shared frame clock:
mobile settings previews resume when visible, without advancing hidden scenes.
The decorative face remains hidden from assistive technology; the widget's
translated controls retain keyboard operation and mobile positioning.

Behavioral coverage includes actual SVG continuity, quiet thinking, all styles,
independent brows, family direction at different frame rates, long seeded idle
simulation, interruption, response release, malformed/replayed events, actual
audio, refused capabilities, nested/parallel operations and emitter failure.
PostgreSQL integration exercises idempotency and JSONB commit/rollback. The
hermetic `e2e/smoke/chat-avatar.spec.ts` exercises draft/success/failure/unknown
outcomes, reload, mobile bounds, reduced motion, keyboard controls and axe.
It also observes a spontaneous scene starting and finishing in the actual
widget, across the Chromium, Firefox and WebKit configurations.
The real-component visual laboratory is separate from product UI.

### Volume, proportions and ambient context

The head now has its own critically damped yaw/pitch springs. The eyes lead;
the head follows the actual gaze channels, including authored thought and
activity patterns. A shared perspective parent carries eyes, brows, jaw and
props at distinct depths. Each skin retains its material and silhouette.
The original, subsequently retired Smiley used a counter-rotated lit sphere and
an independent facial plane. That renderer is no longer part of the catalogue;
the current companion projection is described in
[ADR-340](ADR-340-Native-Avatar-Volume-From-Reviewed-Offline-Art.md).
The mouth's compact anchor and restrained jaw travel are checked against the
painted SVG contour and eye bounds, rather than just CSS declarations.
Resting temperament deliberately exaggerates signed mouth curvature, eye
compression and brow asymmetry so that mood reads at widget size. Actual work
and response poses attenuate that layer. Thinking holds a raised brow, unequal
eye openings, a short off-centre mouth and a gentle inclination; it never uses
repetitive jaw movement. Retargeting preserves the springs' position and velocity.

`GET /briefing/companion-context` is authenticated and reads only the account's
weather section from the existing briefing cache (and, since 2026-11-13, the newest
observation other reads of the person's place left: see « the face takes the weather
LIA reads » below). It never initiates a weather fetch, connector call, model call or
location request. Hidden, missing, failed,
future-dated, malformed and expired sections produce no weather. The projection
contains temperature, condition code, wind and the original snapshot validity;
it omits location, descriptive text and forecasts. Expiry follows the source
section TTL; polling does not refresh that timestamp.

The chat widget owns one abortable, visibility-aware request lifecycle. The
environment store is ephemeral and clears on unmount. The rig combines fresh
weather with the account's civil clock, caches the local minute, and releases
stale weather even when reduced motion has stopped continuous frames. These
clock bands approximate dawn/morning/noon/afternoon/evening/night; they are not
astronomical sunrise or sunset. A cold briefing cache therefore gives time-of-day
lighting but no invented weather, until fresh cached weather becomes available.
The host's idle attitude reads the same account hour; it cannot doze on the
device's midnight while the face is lit for the account's morning. Browser
scenarios pin their clock and exercise night separately, so a test run crossing
midnight cannot silently select a different acting state.

One weather intention wins: observed precipitation/fog, then strong wind, then
temperature. Thresholds and the exact strict temperature boundaries requested
by the owner live in `components/eyes/environment.ts`. Rain has an umbrella and
drops; a storm has a cloud, slanted rain and a steady pale bolt. Cold uses a
scarf, freezing uses frost and a breath puff, and snow has drifting flakes.
Warm weather uses a fan; strong heat uses a temple droplet. Mist, a windblown
leaf and a night crescent complete the motifs. Every condition has a distinct
channel. Particle phase and sway come from the shared rig clock, with a fixed
phase that cannot accelerate during a spring crossfade. Weather
props yield to active work and the answer's hold/release, while ambient light
remains. No strobe, lightning flash, snowfall canvas or confetti is introduced.
Reduced motion keeps a static contextual pose.

`e2e/smoke/chat-avatar-environment.spec.ts` verifies the actual head projection
and compact mouth across skins, plus weather/answer priority, expiry and the
account timezone. Browser tests also verify distinct visible weather motifs,
actual motion and a live switch to reduced motion. HTTP tests cover account isolation, hidden preferences,
malformed cache entries, Redis failure and unauthenticated access. No new
dependency, database schema, prompt, token allowance or provider quota is needed.

### Follow-up: native body volume (2026-10-12)

[ADR-340](ADR-340-Native-Avatar-Volume-From-Reviewed-Offline-Art.md) extends the
native presentation with an alpha-derived body proxy, projected facial wrappers
and shared contextual materials. It retains this ADR's rig clock and
visibility/motion owner. The
[native volume guide](../technical/NATIVE_AVATAR_VOLUME.md) documents source
ownership, resource fallback and the limits of approximate rear anatomy,
DOM/SVG facial occlusion and the deliberately front-composited scarf.

### Follow-up: quieter, directed acting (2026-11-08)

The owner-authorized [finishing pass](../superpowers/specs/2026-11-08-avatar-finishing.md)
retains the clock, springs, artwork and lifecycle. It removes the full-turn,
somersault, jig, dizzy and brow-groove scenes and the autonomous slapstick,
head-wobble and eye-hop gestures. The catalogue is defined by `SKETCHES`,
with explicit validation at the public scene entry; a stale removed name
cannot start an empty or unknown performance.

The remaining scenes have character-specific timing, readable holds and
quiet recovery. Breathing and gaze remain active. Speech accents follow the
generated phrase, without an unrelated periodic eye bounce. Conversational
nod and thoughtful inclination are host-only cues, never random idle picks.
These are repertoire and direction changes within the existing architecture;
they add no animation clock, dependency or generated assets.

### Follow-up: what the face costs to draw (2026-11-11)

Measured on the public page (production build, real GPU), the visible avatar
took about half a second of main-thread work per second of rest, three quarters
of it style recalculation. The cause is structural: the rig's channels are
inherited custom properties on the avatar's root, so every write restyles the
whole tree below it — one hundred elements under the default avatar, fifty-nine
of them weather slots and scarf facets with nothing to show. With a processor four
times slower the page fell to seven frames a second and the face's own clock
ran at less than half speed.

Three rules follow.

**A prop without weather is out of the style tree.** `data-weather-props` is
the one switch: the announcement that installs a slot's bitmap also puts the
slot back in the tree, and until then it is `display: none`. Nothing changes to
the eye — an unannounced slot had no bitmap and painted nothing. Tried live on
the same page before it was written: 44 to 55 % less style recalculation, 36 to
40 % less main-thread work. `AmbientAccessories.test.tsx` holds the three
tables together (slots mounted, tokens announced, rules keyed on them), and
`e2e/smoke/chat-avatar-environment.spec.ts` reads the computed display in a
browser and caps the elements that have a box under the default avatar, a
ceiling that only goes down.

**A long frame is carried whole.** The shared clock used to truncate any frame
to `MAX_FRAME_MS`, which is slow motion for as long as the page is busy. It now
carries the elapsed time up to `MAX_CATCH_UP_MS`, and the binding integrates it
through `stepInSlices`, in equal slices no longer than the old cap: the face
ends where the time takes it, reads every beat on the way, and is drawn once.
A frame within the old cap is one step, exactly as before.

Measured after the change on the development build, the old sheet against the
new one in the same session: 94 elements with a box against 35 under the
default avatar with no weather, and half the style recalculation; with a
processor four times slower, 12 frames a second against 47, and the face's
clock within 0.2 % of real time where the old cap would have lost 6 seconds
out of 20.

**A scarf the native cloth draws has no fallback in the tree.** That first
measure showed the limit of the rule above: with cold weather the gain fell to
4 %, because the fitted fallback scarf stayed in the tree, invisible, while the
native cloth was drawn (73 elements with a box, 38 of them the closed collar:
thirty-two facets, the knot, the tail and their wrappers).
`data-volume-scarf-ready` now takes the fallback out with `display: none`
instead of hiding it, and the avatar is as light with a scarf as without one
(35 elements): over five windows of twenty seconds, the median style
recalculation went from 170 ms per second to 89, against 101 for an avatar with
no weather. The fallback is a declaration, so it has no state to catch up on:
the instant the cloth is lost it is back, sheared as the cloth was. The browser
scenario proves that by losing the graphics context while the cloth trails; it
can no longer read the fallback WHILE the cloth is drawn — an element under
`display: none` reports no transform in Chromium and WebKit — and no longer
needs to.

What remains is the tree itself: one write still restyles every element that
has a box. Registering the channels as non-inherited and writing each where it
is read cut the restyled elements from 171 to 70 in a cost-only trial; it
changes the writer and the boundary rule of
[ADR-252](ADR-252-Expressive-Eyes-Animation-Rig.md), and is not done here.

### Follow-up: what the face does with the exchange (2026-11-12)

The rules below come from one analysis (2026-11-11): the craft of the motion was
in place, and the weak points were what the face did WITH the exchange. Each
rule answers a measured defect.

**A face that follows text has no life of its own.** While an answer was being
written the rig was told nothing: the host showed `attentive`, the acting
context said neither `activity` nor `responding`, and the face's own life went
on as at rest. Simulated on 1 200 turns, a comic scene started during 9.7 % of
the seven-second answers and 36 % of the thirty-second ones; in a browser, a
startle in the middle of the text. `ActingContext.attending` now says it — a
turn is open, or the person is typing (`eyesSignalsStore.isAttending`, the one
predicate) — and the rig stands mimics and scenes aside, counts none of that
time as rest, and drops a scene in progress when the text starts. The pose is
untouched: following is not a task.

**Letting go of the text is a silence, not a cue.** Every keystroke already
paused the rig's life for 1.5 s (`body-motion-binding.ts`), and a mimic that
came due meanwhile was only held back: over 200 seeds, after thirty seconds of
typing, it played 1.5 s after the last key in 199. A face that answers every
pause in the typing reads as a tic. On release the rig draws a whole silence
(`drawMouthLifeSilenceMs`), never the second or two that follows a beat — none
was played. The same measure after the rule: 0 in 200 within six seconds.

The end of ANY pause is the same moment (follow-up of 2026-11-13). A click, a
key or a wheel event anywhere pauses the life for 1.5 s, the pointer on the
face pauses it while it stays, and a mimic that came due meanwhile played the
instant the pause ended: after thirty seconds of scrolling, 1.5 s after the
last wheel event in 200 seeds out of 200; when the pointer left the face, at
once in 200 out of 200. `tickMouthLife` reads the end of a pause on its first
tick after it and, when a mimic is due, draws the same whole silence: 0 in 200
within eight seconds, both ways. A pause that ends before the mimic is due
leaves it its own time. Proven by seven unit mutants (the release removed, read
on every tick, drawn as a beat or a fixed wait, either pause forgotten, the
pause never remembered).

**A look names its target, and the screen says where it is.** The engine cannot
know where the text is: that depends on where the person parked the face. A
frame names WHAT it looks at (`ExpressionFrame.target`), the screen declares
the thing (`gazeTargetProps`, on the answer being written), and
`locateGazeTarget` is the only reader; `gazeToward` is the one geometry, shared
with the cursor parallax. A frame that names a target is held on it: no wander,
no idle gesture, no cursor. The browser scenario holds an answer open longer
than the longest wait before a first scene; served the predicate mutated to
`false`, it fails on a scene twenty-five seconds into the answer.

### Follow-up: the wait (2026-11-12)

A turn lasts 25 to 29 seconds at the median (thirty days of production, 288
answers), and the face spent them on one pattern per tool family, repeated —
the family `reading` being 142 of the 187 answers that carried execution
evidence. The most watched moment was the least varied. Four rules, none of
them a new gesture: the vocabulary is the rig's own.

**A message is acknowledged.** When the status the face sees turns to
`sending`, it plays `perk` — attention is a brow raise before it is anything
else. A person who was typing already has an attentive face, held for longer
than any hold: the thought that follows the send would land in the next frame
and cut the beat. The acknowledgement re-arms the expression hold, so the
thought waits for it (`MIN_EXPRESSION_HOLD_MS`, as any non-urgent arrival
waits for the expression before it).

**A face that reads, reads.** While a `reading` tool runs the eyes walk
lines: rests of a quarter to under half a second from left to right, now and
then a second look at a word, a quick return to the start of the next line, a
little lower, and — the page read — the eyes up from it for a moment
(`readingGaze` in `rig/direction.ts`). Every page is drawn anew when the
pattern comes round. The line is half as wide as a search is: the head follows
the eyes, and a reader's head stays where it is.

**A long thought changes attitude.** `thoughtPattern(random, turn)` goes
through three — the eyes up and away, down and inward, the head to one side —
never the same twice in a row, and the rig counts the turns of ONE stretch of
thinking: a new thought starts over, up and away. It stays inside the moving
hold's pixel budget (ADR-264): the inward look was drawn at 0.16 rather than
0.2 because the brows follow the gaze, and at the largest size the brow travel
of a minute of thinking came to 2.003 px against 2.

**A tool that comes back with a result is marked.** A blink, as at any
boundary of attention, and the brows lift (`brow-twitch`). On EVIDENCE only: a
`succeeded` or `prepared` end; a failed, cancelled, waiting or unknown one
marks nothing. The mark is keyed on the tool's identity, not on its time — the
delivered answer stamps the same evidence again, and a recall is not another
tool — and a face mounted after the tool finished marks nothing it did not
see. While another tool still runs the rig keeps the brows to the work and
only the blink plays. The decisions are pure (`exchange-beats.ts`); the host
plays them on the one channel an answer's accent already used. The 3D world
keeps its own beat, a hop on an accomplished action.

### Follow-up: an answer handed over (2026-11-13)

A delivered answer landed on a face that did nothing, or less. 94 % of the
answers measured (thirty days of production, 288 answers) declare no accent, so
no beat played; a factual one — half of them — earns `neutral`, the face the
character rests on, and the reaction put that face's own smile out (0.26 down to
0.12 on the bench: `available` and the temperament's weight both read
`responding`); a careful one floated the « … » thinking bubble and looked away
as if it were still working; and the face's own life waited for the reaction's
hold AND its release, ten seconds. Among three proposals the real stack played
side by side on a bench, the owner chose « la remise présentée »:

- **The answer is presented.** With no accent declared, the register supplies a
  presentation (`deliveryGesture`, `tone.ts`) in one of five manners
  (`rig/delivery.ts`): a look at the answer with, for a character with hands,
  an open hand that presents it, then the register's own « voilà » — a blink, a
  nod, a smile up to the eyes and an exhale for a factual answer; a brow flash
  and a crisp nod for an assured one; an inclination and lifted inner brows for
  a careful one; a little hop for a warm one; a bow for a sorry one. A declared
  accent still plays as declared, and a sparkle stays an accessory.
- **Then it is handed over.** Three seconds in (`HAND_OVER_AFTER_MS`), « à
  toi »: the face leans in a little, lifts its brows a hair and waits
  (`listen`) — unless the answer is no longer the one it holds or the person has
  started writing (`mayHandOver`). Its idle life waits for it (`faceIsTaken`):
  a wandering look in the middle would take back what it hands over.
- **A delivered answer keeps its face.** A factual answer keeps the character's
  rest smile and the temperament (`answering`, `direction.ts`); the thought
  bubble and the looks away of a thought belong to work, never to a careful
  answer already delivered (`frameEmote`, `startPatterns`).
- **The face is its own again when the hold ends** (`isReactionHeld`, four
  seconds), not when the release has faded: the tone keeps fading, the life
  resumes.

Measured traps shaped the tapes. A pitch of a few degrees of a flat painting is
invisible on a sculpted character, so every nod — the `nod` accent included —
is the head dipping with the eyes and the body (`nodTapes`). An eye smiles by
its squash, never by a lower lid that only crops a sculpted eye's transparent
margin. A delivery's two lids close within 18 ms: 60-70 ms apart read as a wink
on a recording. And the hand travels to its joints' envelope and no further
(`LIMB_LIMITS`: 18° for the arm, 14° for the wrist), where the bench's 42° was
stopped dead by the clamp mid-gesture.

One trap shaped the host. The rig interrupts every beat on a new expression,
and the answer's own face lands a commit after the store learns of the answer
(the chat page's status changes first). Played at once, the presentation of
every streamed answer was wiped a few milliseconds in — measured in a browser:
neither the arm, nor the head, nor the look moved. The delivery is now PARKED,
like the accessory before it, for the frame that lands its answer's face, and
plays in that same commit, after the arrival (`deliverOnArrival`).

Proofs: unit tests on every rule, 28 mutants on a mirror; the browser scenario
`chat-avatar.spec.ts` « hands its answer over » follows an answer as it is
written, then reads the PAINTED eyes, 6.5 px lower at the largest size while
the look holds against −0.2 px for a presentation served looking up — the
samples taken with the lids down are set aside, since a spontaneous blink moves
the paint as much as a look — on Chromium, Firefox and WebKit; four mutants
served in flight each fail at their own step (no presentation, the look
reversed, no hand-over, a hand-over that cuts the presentation).

### Follow-up: weather the character plays (2026-11-12)

The weather was set down BESIDE the face — a scarf, an umbrella, three flakes —
and the character did not react to it. Three reactions now, with what the rig
already owns: no new prop, no new scene, and observed weather only
(`environment.ts` stays the one door, and it invents no climate).

**In the wind the eyes narrow.** The head already leaned into it; the eyes now
give up a seventh of their height and the brows come down with them. Like the
lean, the squint is not a mood: it holds through work and through an answer,
and a sleeping face is spared. The brows it lowers stop above the eye like any
other (the limit of the rule below).

The first version squashed the eye (`sy`), and its tests read the channel: the
channel moved, and a SCULPTED eye did not lose one pixel — measured in paint,
the default character kept 100 % of its height in a full wind, because a
sculpt never scales vertically and the clip a squash drives fell inside the
texture's transparent margin. The sculpted eye now takes the wind in its own
clip (`eyes.css`, `.lia-spirit-companion .lia-eye-shape`): lids that reach
12 % of the painted band from above and 5 % from below, counted from the
painted edge (`--spirit-eye-crest`, the same margin at both ends of the
texture), and that reach nothing at all with no wind — at rest the sculpt is
pixel-identical to what it was. Measured in paint at the largest size: the
default character keeps 85 % of its height, the copper robot 87 %, the human
86-88 %, a drawn face 86 %. The browser journey photographs the eyes alone,
calm then windy in the same page (a reading observed later than the page
opens), under reduced motion so that no blink or mimic moves the paint, at
the largest size because a seventh of a 13-pixel eye is two pixels.

**When something starts falling, the face looks up, once.** Rain, a storm or
snow that ARRIVES earns one look at the sky, the head following the eyes
(`skyGlanceTapes`). Cold, wind, fog and heat are felt, not watched. The look
is remembered on the shared clock that already outlives a mount
(`SketchClock.sky`): rain that has not stopped is no news to a companion
mounted again on the next page. A face that is taken looks when it is free
again: the look is asked from the resting tick alone, and only the look marks
the weather as seen. A sky that stays empty for five minutes of rest is
forgotten (`SKY_FORGOTTEN_MS`), so rain that comes back is news — but not a
sky that is empty for a moment: a face that knows no weather is, most of the
time, a face whose reading has not come back yet (the companion was just
mounted, the snapshot is being refreshed), and forgetting at once made every
page a new rain.

**In the cold it sneezes more than its share.** `pickActingSketch` weighs the
sneeze like a character's favourite scene while the reading says cold or
freezing; every other scene stays reachable and the scene's own memory still
forbids two in a row. The picker reads the conditions the props read, through
ONE function (`weatherConditions`, `rig/ambient.ts`: the flags, or the
dominant feeling of a context that carries none) — a cold rain is worn as a
scarf and an umbrella and played as a sneeze, whichever feeling dominates.

The look at the sky was measured in paint as well: at the largest size the
default character's pupils rise 5.8 pixels and its eyes 4.3, the head tilting
back with them; the copper robot's 6.0 and 2.0, the human's 3.3 and 2.7.

Left out then, and why: a sun, clouds and raindrops that fall are ARTWORK,
and a shiver is a scene to author, not a parameter. Both were proposed on a
bench rather than improvised; the artwork came the next day (below), the
shiver was not chosen.

### Follow-up: the weather happens around the face (2026-11-13)

Among three proposals played by the real stack on a bench, the owner chose
« le petit ciel »: the weather no longer stands beside the face, it happens
around it.

- **The umbrella opens** as its rain arrives — a pop past its size, then
  settled — and rocks a little in the hand. The opening is read from the
  rain's own weight (no event, so a page mounted in the rain shows it open
  as it fades in), and the slot is opaque from a quarter of that weight:
  inside the engine's fade the pop was spent unseen (scale 0.53 at 11 %).
- **A cloud rains on it**, its drops falling three times a fall, and drops
  gather at the umbrella's rim, hang and fall. **The snow falls from its own
  cloud**, past the face, drifting. **A gust** crosses — two lines and a leaf,
  in front of the body. **The freezing cold shows a breath**, born at the
  mouth by the mouth's own anchor (`--companion-mouth-y` on a sculpted face)
  and in front of a monitor's screen.
- **An ordinary day has its sky**: by day, a sun beside the head on a clear or
  a cloudy day, and a cloud passing before it on a cloudy one. Never at night
  (the crescent is there), and never a condition the face plays: `skyAt` reads
  the sky apart from `weatherFlagsAt`, which a clear day leaves as it was. The
  sky does not ride the head: it stays where the day is.

One clock, still. `ambientMotion` publishes three sawtooth phases — the fall
(3.2 s), the drop (a third of it) and the drift (three times it), whole
ratios so every particle wraps where it is invisible — parked at 0.5 when
nothing moves; the sheet derives each particle's path from one of them. Its
fractional part is written with clamps (`mod()` is unknown to Chrome before
125). Under reduced motion what only exists by moving is not drawn, and the
gust's leaf waits beside the face as the wind's leaf always did.

The artwork is the bench's own vector drawings, shipped as files
(`public/avatars/sky/v1`, seven drawings, 5.4 KB) that the sheet installs only
on the weather's announcement: drawn inline, each element of a drawing would
be restyled on every frame the rig writes. For the same reason the sun is
drawn on two boxes — its slot paints the glow and the core, the rays that
turn are the one part apart — and the cloud paints itself. Measured before it
was allowed (dev server, BIP, median of three 20-second windows): 35 elements
with a box and 132.5 ms/s of style recalculation with no weather, 37 and 133.7
under a clear sky, 38 and 138.3 under a cloudy one, 46 and 155.2 in the rain,
48 and 137.4 in the snow. The ceiling of an avatar with no weather stays where
it was; the sky of an ordinary day is allowed three boxes more
(`chat-avatar-environment.spec.ts`).

Proofs: unit tests on every rule and 21 mutants on a mirror (among them a sky
that never moves, which no test caught until a clear day alone had to turn
the sun's rays); browser journeys on Chromium, Firefox and WebKit — a sun
painted warm beside the head and a cloud passing before it within the
allowance, a night with its crescent and no sun, rain and snow that fall from
their clouds and are not drawn under reduced motion — and three mutants served
in flight, each failing at its own step (a sun at night, phases parked, the
particles drawn standing still).

### Follow-up: the face takes the weather LIA reads (2026-11-13)

Owner report: the avatar only took a new weather after the page was reloaded.
Measured before anything was changed: the companion borrowed ONE reader's cache,
the dashboard card's, kept an hour, and only the dashboard and the radio filled it,
while the heartbeat (95 reads a day on one measured production account), the proactive
discussions, the weather routines and the chat's own weather tool read the same
place and kept it to themselves. On the chat, an hour after the last dashboard
visit, the face lost its weather until a page rebuilt the card; its quarter-hourly
read found nothing newer to read.

**One door.** Every read of the PRESENT conditions at the person's own place —
their position, last known place or home, never a city someone names in the chat —
offers what it observed to `publish_companion_weather`
(`connectors/companion_weather.py`): a temperature, a condition, a wind speed and
the provider's instant, no place. A script on the Redis server keeps it only when
it is newer than the kept one (readers run at their own pace, on several workers),
for as long as it is the present (`PRESENT_WEATHER_FRESH_SECONDS`, an hour), and a
kept observation is said on the person's channel (`companion_weather`). Every
module that reads the present weather calls the door or says why it must not
(`test_companion_weather_readers_guard.py`, read from the syntax tree).
`companion-context` answers the newer of the card's weather and the kept
observation; a hidden weather card hides both. Both sides read ONE rule of what is
still the present (`is_present`), and the endpoint's model extends the observation
rather than restating its bounds. The door never fails the read that offered it: an
unreadable instant, one no `datetime` can hold included, is read as now, and an
unreadable wind as no wind. No provider, model or location call is added: the face
shows what LIA read anyway.

**The open page.** The stream hands the signal to the companion's store
(`requestRefresh`), never to the notification list; the owning hook reads at once
instead of at its next quarter hour, reads once more when a read was already on
its way (it may predate the newer observation), keeps a request made out of sight
for the moment the page is looked at, and a stream that was down asks once when
it is open again.

Proofs: unit tests on the door, each of its five readers and the endpoint; the
newer-wins script on a real Redis (twenty racing writers leave the newest, the same
observation offered twice is said once); 37 server mutants applied in memory, all
killed but one redundant line, since removed (a missing temperature is already refused
by the model), and 14 on the page's side, all killed but one equivalent (a reset
clearing a counter the hook reads again right after); a browser journey in which the
weather changes while the page stays open (`chat-avatar-environment.spec.ts`, « takes
the weather LIA just read, with no reload ») on Chromium, Firefox and WebKit, red when
the store ignores the request or the stream ignores the signal.

### Follow-up: the frost crown is worn (2026-11-13)

Owner report: the frost crown of a freezing day is miscalibrated on the heads
of the different models. Measured on every head before anything was changed
(the paint, xl, a static pose, with the journey below), it was worn right on
one head of seventeen (Boulon's female). On twelve its feet sat deeper in the
head than its band is thick, 0.2 to 0.8 em — two horns on a forehead — and on
the monitor it painted over the brows; on three it hung in the air beside a
tuft or a leaf; on one it came down beside the eyes. Two causes. It was SEATED
on the crown landmark, the top of the opaque silhouette, which on half the
heads is a ribbon, a leaf or a tuft, with a face-relative limit that put it on
the forehead of every wide head; and it was SIZED like the other props, a
scale tuned for a raindrop or a fan, so a round head twice its width wore it
as two horns.

**The rule.** The laurel's artwork is two bands whose lower edge is an arc:
worn, it sits ON TOP of the head. Each band rests on the painted edge — at its
foot it crosses the edge, neither in the air beside the head nor diving into
it — the whole crown ends above the face, and the middle stays free for a
tuft, a leaf or a bow. Each head has its own seat (`layout-profiles.ts`,
`LAURELS`, a centre and a scale): as large as the bare artwork suggests where
the head leaves room, seated inside the range these rules accept and at least
0.04 em from either end of it, so every engine paints it inside. The sheet
seats a square of the artwork's size on the published
centre; the native volume projects the same centre (`physical-prop-writer.ts`).
No other prop moves: the crown landmark still places the emote, the rain, the
storm, the snow and the night.

A first fit on the artwork alone — the bands' outer halves on the head's
contour by least squares — looked right on the drawings and wrong on the
screen: the eyes and brows are drawn by the rig, not by the artwork, and on
six heads that fit brought the bands down beside the eyes, on two onto the
brows. The seats are therefore measured on the PAINT of every head with its
face: the head, the eyes and the brows photographed apart, the crown tried at
every height and scale offline with the very rules the journey applies.

Proofs: the paint is the oracle (`chat-avatar-environment.spec.ts`, « the frost
crown is worn on every head »): on every model and gender, a static pose at
the largest size, each band's foot is measured by how deep it is in the painted
head — its distance to the nearest pixel that is not head, never a column's
top, which a steep side or an overhanging leaf makes meaningless — and must be
neither in the air nor deeper than the band is thick; the crown may not touch
an eye or a brow and must end 0.04 em above them, at most 45 % of it may be
painted on the head, and it is centred. Green on the seventeen heads; served
in flight, the old seat fails on sixteen (the one it wore right passes), one
head's seat moved fails on that head alone, and the scale ignored fails the
four heads it lifts into the air. Six unit mutants on the writer and the
published tokens are killed.

### Follow-up: the weather the character lives (2026-11-13)

Owner's choice: the four scenes of the bench's « the character lives its weather »,
left out when the played weather was wired, were wired the same evening — the first
drop and the caught flake REPLACING the look at the sky for rain and snow, a storm
keeping its look.

**The scenes** (`rig/weather-scenes.ts`). The first drop of a rain lands on the head:
a flinch on the very beat it lands (`DROP_LANDS_MS`), a blink, a look up — and only
then the rain shows (`weatherRain` is held back for `RAIN_HELD_MS`), so the cloud
comes and the umbrella opens as the face looks up at them — then relief. The first
flake of a snow is PURSUED by the eyes (a moving target on a linear trajectory a beat
ahead, never steps that would make them hop) down to the root of the nose: an « oh »,
a blink, a delighted smile; the snow itself is not held back. One drop is no news in
a storm: it is looked up at. At rest, the cold offers a shiver, and a clear, mild day
by day — nothing felt, no heat, wind or cold — the sun on the face: eyes closed, a
content smile, two slow breaths (`restingWeatherScenes`). An offered scene joins the
draw as likely as a favourite, and only then (`pickActingSketch`). A soft body ducks
under the drop; a rigid casing cannot (its elasticity is 0.12), and its head nods.

**One clock.** A greeting is recorded on the shared `SketchClock` like any scene
(`data-scene` names it) and ends the resting tick, so nothing drawn on the same frame
replaces it; it never re-arms the clock, so the resting scenes keep their schedule.
A scene that carries a prop is never warped (`carriesProp`): a per-channel warp
would part the drop from the flinch. A blink never opens the eyes a scene holds:
measured on the bench's paint, a blink during the sun's hold opened the eyes for an
instant, then let them close again.

**The props.** The drop and the flake are PATH channels (`weatherDrop`,
`weatherFlake`: 0 where they appear, 1 where they land, past 1 a splash), step
channels on a linear trajectory, announced like every prop (`drop`, `flake`),
mounted in the head beside the others, with no box outside their scene, drawn from
files (`drop.svg`, `snow.webp`). Each is seated on the paint of every head: the drop
lands on the first painted row anywhere across its own width (`HEAD_TOPS` — on the
female Spirit, the edge of the ribbon that reaches the middle); the flake on the
root of the nose (`FLAKE_YS`), because below the eyes the mouth leaves no room on
most heads (0.008 em on two of them) and between them the eyes leave 0.13 to
0.20 em; the screen's six drawn faces share one free band, below the eyes, from
0.444 to 0.453 of the frame.

Proofs: unit tests on the scenes, the draw and the rig (the flinch on two materials,
a pursuit that never stops, eyes kept shut under a blink, a greeting a due scene
cannot replace); 28 mutants on a mirror, all killed. On the paint
(`chat-avatar-environment.spec.ts`), on Chromium, Firefox and WebKit: on seventeen
heads the drop lands within 0.05 em of what it meets first, down the middle, never
on the face, the umbrella after it; on twenty-two faces the flake settles on the face
and on no eye, brow or mouth; under reduced motion nothing is carried. On the bench's
paint (the working tree with the door to its rig), every scene on every head, on the
three engines: visible — the eyes, brows and mouth differ from their rest by 12
to 110% of their pixels — the sun keeping the eyes shut through its hold for
every pace a resting scene may take, and no brow on an eye at any instant.

Limit: the first drop of a session fetches its artwork as it starts to fall (a slot
installs its bitmap only once announced, so choosing an avatar downloads nothing):
on a cold cache it may show only part of its fall; the face's flinch keeps the beat.

### Follow-up: a mouth that opens on the voice it hears (2026-11-13)

Owner's choice, the third lot of the evening: the speaking mouth driven by the real
sound. Until then a speaking face made up its syllables while the audio played, in
rhythm by luck at best.

**One door** (`lib/audio/voice-envelope.ts`). Every voice LIA speaks with taps its
sound there: the buffer source the chat's voice comments play (`AudioQueue`), the
live session's worklet node (`PcmStreamPlayer`), and a WebRTC session's remote voice,
which its own element plays (`RoutedLivePlayer`'s native sink) — tapped on the context
the local player LENDS (`tapStream`), created and resumed on the person's gesture,
because a context made when the stream arrives could stay suspended (the iOS rule the
players already follow). A tap is a PARALLEL branch to an analyser: the sound path is
untouched, and a sound that cannot be tapped still plays. A voice the speaking avatar
carries is not tapped: on the chat, the eyes are hidden while it is present.

**What the door reads.** The face reads ONE level (`voiceLevel`): the RMS of a 10 ms
window in dBFS, mapped from `VOICE_FLOOR_DB` (−35, the mouth shut) to −12 (a full
voice), the loudest when several voices play. It is read as the person HEARS it when
the face SHOWS it: an analyser sees what the graph renders, heard the context's
latency later (`baseLatency + outputLatency`: tens of milliseconds on speakers, a few
hundred on a wireless headset), and the face shows what it reads `VOICE_LEAD_MS`
(60 ms: its envelope, its spring, its next frame) after; so a tap holds up to 0.4 s of
sound and reads the latency back less that lead, never a sound not rendered yet. One
read costs 26 to 37 µs in Chromium (1 to 2 µs with the former 512-sample tap), 3 µs in
Firefox: a fraction of a percent of a frame, and only while the face speaks. The door
answers null when no voice is heard — none tapped, none on a running context (a
suspended analyser reads nothing, which is not a silence), none that reads as a number,
none an engine can read (it throws nothing onto the face's frame), and none that heard
any sound at all (above −70 dBFS) in `VOICE_BLIND_AFTER_MS` (1.5 s) of listening: a
voice that plays sounds sooner, so that tap is BLIND, and the face speaks on its own
rather than with its mouth shut. Only listening counts, so a pause between two
speeches never blinds a tap, and a tap that heard once is trusted through every
silence after. The door answers nothing else, so the rig reads it as it comes.

**The rig** (`sampleVoice`). Only a speaking face hears. The opening follows the level
with a 15 ms attack and a 20 ms release (`VOICE_ATTACK_MS`, `VOICE_RELEASE_MS`), above
the pose, up to `SPEECH_OPEN_MAX`, outranked by a beat alone; the generated speech
keeps the shape of its words (width, curve, corners) and takes the opening back
whenever the door answers null. Reduced motion keeps a still face.

**Tuned on real voices.** Two French sentences spoken by the local Windows voices
(free, offline), laid on the real rig frame by frame, then played in the browser as
voice comments. The first tuning (−45 dB, 25/50 ms, no lead) followed the sound
closely (correlation 0.91) but 60 ms late, and hung open across syllables: open 60 %
of the time, 1.1 clear openings a second, 2.3 visible beats for 3.6 to 3.9 syllables.
The kept tuning, measured in the browser: the mouth on the heard sound to within
−10 to −20 ms before its frame is shown, correlation 0.95 and 0.91, 2.1 clear openings
a second, open 44 % of the time, travelling as much as the generated speech (2.3 a
second against 2.2); on the real rig, 3.2 visible beats a second. The generated
speech, on the same voice, has no relation to it (correlation 0.06 to 0.15). A video
puts the two side by side on the same voice.

Proofs: unit tests on the door (latency and lead, a quick device, a wireless headset,
an absurd or unreadable latency, a blind tap, a soft voice that is not blind, a pause
between speeches), the rig (envelope asymmetry), the hook (a living face hears, a
preview does not), the three players and the routed sink (tap, release, replacement,
takeover by the avatar's capture); 45 mutants on a mirror, 44 killed, one equivalent
(the speaking pose holds the mouth shut, so the opening above it is the opening itself). In the browser
(`chat-avatar-voice.spec.ts`), a voice comment of three 900 ms tones parted by 900 ms
silences: the mouth held open on each tone and shut through each silence, on a drawn
head and a sculpted one, then photographed open on a tone and shut in a silence — on
Chromium and Firefox, at one device pixel per CSS pixel (a sculpted head painted at
twice the density starves the frames a timeline is read on: 13 a second on a loaded
host). With the tap made impossible, the same journey flutters in short runs: the
oracle fails. A mechanism probe on the three engines as Playwright launches them: a
parallel analyser on a playing source hears it in Chromium and Firefox; Playwright's
WebKit on Windows has no Web Audio at all, so no voice plays there and the journey
says so and skips.

Limits: the WebRTC sink is proven by its unit tests and that probe, not by a WebRTC
journey; a browser that reports no latency (Safari gives no `outputLatency`) is
compensated for its graph alone, and a Bluetooth latency the device underreports is
compensated as reported.

### Follow-up: a face that speaks looks at the person (2026-11-14)

Owner report: in the spoken modes the eyes went from left to right while the voice
played — « that is not natural, it is speaking to me ». A loop of `useEyesBehavior`
walked the gaze along a line, four stops and a quick return every 340 ms, for as long
as the expression was `speaking`. It was written when `speaking` meant « the answer is
being written » — the eyes « wrote » it — and it outlived that meaning: `speaking` now
requires actual audio playback, so the face read a text aloud to nobody.

**Decision.** A face that speaks is directed at the person. The loop and its table
(`readingGazeAt`) are removed; the gaze holds where the frame puts it, and a glance
under way when the voice starts comes back, speaking leaving the wandering family as
every directed expression does. The mouth still opens on the voice heard; blinks and
breathing stay the rig's. The eyes that READ are the wait's (`readingGaze`, while a
`reading` tool works), never the speech's. Pinned by `EyesWidget.test.tsx`: the gaze
over twelve former beats, the idle life's own glance, and a glance the voice interrupts.

Second report, the same day: with a spoken comment or a Live voice, the lips followed
nothing over the first words of an answer, then followed the voice. The answer's delivery
(2026-11-13) was playing under the voice: its presentation stayed posted when `speaking`
arrived, and its « à toi » fell due three seconds after the answer landed — in the middle
of a sentence, for four seconds — moving a mouth, a gaze and a hand the voice was to move.
A face that speaks plays no delivery: on the frame that lands `speaking`,
`deliverOnArrival` drops the beat under way and the hand-over still owed; the voice hands
the answer over itself. The delivery still parked goes too: played when the voice pauses
between two phrases, it would be cut by the next one. Pinned by four tests of
`EyesWidget.test.tsx` (« an answer delivered »), each part of the rule killed by its mutant.

### Follow-up: the things the face looks at are where the screen shows them (2026-11-12)

Two looks were still directions written in the engine: down at the field the
person types in, top-right at a notification. A face parked beside the thread
looked down at nothing while the field was to its left; and the notification
was never top-right — the toaster shows it at the top CENTRE in the chat, and
outside the chat it shows on the companion presence, bottom right.

The rule of the answer being written now holds for both. A frame names the
thing (`target: 'input'` while the person types or a message leaves,
`target: 'notification'` on a ping), the screen declares where it is
(`gazeTargetProps('input')` on the composer's field, `'notification'` on the
companion presence and on its restore dot), and `locateGazeTarget` stays the
only reader. The toaster is the one thing no screen can decorate: its toast
in front (`data-sonner-toast`, `data-front="true"`, never one on its way out,
`data-removed="true"` — the attributes of the pinned library, read from its
source) is declared beside the attribute, in `gaze-target.ts`. The toaster
comes after the page in the document, so a toast that has just appeared wins
over a badge that was already there. An answer is read at its end, where the
next words appear; a field and a notification in their middle.

A frame that names a target keeps a direction for a screen that declares
none: down for the field, UP for a notification — the toaster's place, where
the old top-right was a guess. Proven by fourteen unit mutants and, in the
browser, by a face parked half-way down the right of the chat: it looks at
the middle of the field, down and to its left; served the frame without its
target, the field read at its edge, or a composer that declares nothing, the
journey fails at that step.

### Follow-up: a brow is never drawn on its eye (2026-11-12)

Owner rule, stated on a screenshot of the copper robot asking a question: the
brows may never overlap the eyes. Measured before anything was changed, on
every character and its twenty expressions, the defect was old and general on
the eight sculpted characters — nine expressions in twenty for the male
variants, eleven or twelve for the female ones (tender, anger, sad, question,
thinking, focused, bored, tired, sleepy; worried, searching and sleep as well
on the female sculpts) — and marginal on the six native faces (a corner of a
brow on `anger` and `focused`, under a pixel).

**The cause.** A native brow hangs ABOVE the visible top of its shape. A
sculpted one was centred ON that line, and floated above the eye at rest only
because the eye's texture leaves the top of its square transparent. A lowered
lid moved the line into the painted eye and the brow with it, up to the whole
of its ink. The line itself was the native formula, a shape squashed around
its anchor, where a sculpted eye is never squashed.

**The rule.** The authored placement holds wherever it already clears the
eye; where it would not, the brow stops a line of skin above the eye's
highest visible point. One transform carries the smaller of the two
(`translate`, `min()`), and the brow's box is as tall as the eye so that the
lid and the anchor — percentages of the eye — keep their meaning inside it:
nothing about a brow is laid out again when the face moves, where `top` used to
follow the lids. The limit is the eye's top edge (`--eye-crest`: the lid line,
or on a sculpt the painted oval when the lid is above it, both pivoting with
the eye), less the skin kept (`--brow-clear`, at the size the viewer sees it:
the monitor draws its face smaller and keeps more), less the room the ink
takes under the top of its box (`--brow-floor`, `--brow-pitch`), less the drop
of a leaning brow against a leaning lid (`--brow-skew`): two lines that lean
together need no more room than two level ones.

**The oracle is the paint.** A computation on the eye's square reads a brow
floating above a sculpted eye as one lying on it — the first probe did, on
seventeen expressions where the picture showed nine. The same frozen frame is
photographed twice, the eyes alone then the brows alone, each as a white
silhouette, and the two are intersected pixel by pixel
(`e2e/smoke/chat-avatar-brows.spec.ts`: seven lowered faces on two characters
through a real turn, and every tenth of a second of a question's arrival,
overshoot included). The readings are in CSS pixels, from the density each
picture actually has: Firefox photographs at one pixel per pixel whatever a
test asks for, and a threshold counted in rows read its one pixel of skin as a
brow touching the eye. Two things are asserted, because either alone lets a
defect through: no pixel shared and a pixel of skin between, and — on a face
that lowers a lid — a brow that still comes DOWN with it (a limit that ignored
the lid kept every brow off every eye, from a distance). What a browser cannot
be asked for every pose — that the sheet reserves what the contours draw — is
held by `rig/__tests__/brow-clearance.test.ts`, which samples `browPath` and
`sculptedBrowPath` over every arch, tilt and weight against the sheet's own
numbers.

Measured after the rule, by the same two-silhouette probe outside the
repository: the twenty-two character variants, at rest values, at the widest
amplitude a register can earn in the liveliest mood, and with the gaze at the
end of its travel in four directions — 132 pages, 5 144 brow-and-eye pairs,
none sharing a pixel, the closest 0.016em apart; the faces that already
cleared their eyes did not move (the copper robot at rest: 0.036em before and
after). Twenty-two mutants of the sheet killed, sixteen by the unit guard and
six by the paint.

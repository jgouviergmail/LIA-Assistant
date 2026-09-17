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

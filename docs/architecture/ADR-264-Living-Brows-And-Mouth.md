# ADR-264 — Living brows and mouth: one breath, coupled organs, a pixel budget

**Date**: 2026-09-05
**Status**: Accepted
**Context**: ADR-252 gave the expressive eyes a real animation rig, and the eyes
read as alive. The brows and the mouth did not, and the owner said so. Measured
with the rig itself before any change (medium size, 30 px, sixty seconds of
rest, six resting expressions): the mouth moved by **0.47 px** of height and
**0 px** of width; the brows moved by **0 px and 0°**; during `speaking` the
brows moved by **0 px**; a blink moved neither organ. The causes were
structural, not a matter of tuning:

- the brow was a **straight bar** — height, tilt, presence — and a bar can only
  tilt. Surprise, joy, tenderness and a question are told by the ARCH, which
  did not exist;
- the brow was **absent at rest** (`browA` rested at 0), and ten of the
  fourteen psyche moods idle on `neutral`. For most of the session there was
  nothing to animate; when an emotion landed the brow APPEARED, on a fade
  (visible at 144 ms, 90 % at 464 ms), while the eye was already 90 % there at
  256 ms;
- the moving hold reached the gaze, the eye slant and the mouth corners, never
  a brow channel — and the mouth's share was ±0.03 of curve, which is 0.23 px:
  present in the numbers and invisible on screen;
- the idle gesture named `brow` lifted the right EYE (`tyR`, `syR`), a vestige
  of the time before the organ. The `wink` tone accent was wired to it;
- no secondary coupling: brows did not follow the gaze, did not follow the lid
  on a blink; the mouth did not follow a hop or a sigh;
- `speaking` had a mouth that flapped and brows that did nothing, and the flap
  never closed: three sines only ever got quieter and louder. Speech stops.

## Decision

### 1. The brow has an ARCH, and it is a channel

`browArc` per eye, unitless 0..1, group `pose` (willed: it anticipates and it
exaggerates). The stylesheet draws it the way it draws the mouth: one element,
a `border-top` band on a transparent box whose height, top radii and side
borders follow the curvature — at 0 the box is exactly its own thickness and
the border fills it, the resting pill; at 1 it is a semi-elliptical arch with
legs that a thin side border keeps from tapering to nothing. The value is
bounded in the sheet (`min(1, max(0, …))`): exaggeration can push a pose past
1 and anticipation under 0, and a radius can be neither. Every recipe declares
its curvature: surprise 0.85, joy 0.5, tenderness 0.45, a question 0.7 on one
side and 0.1 on the other, anger, focus and boredom **0** — a pressed brow has
no curve.

### 2. The brow is PRESENT at rest, faintly

`browA` rests at 0.5 with a hint of arch (0.12), reversing ADR-252's "invisible
on a neutral face". The reason is the one measured above: a brow that only
exists once an emotion lands has nothing to do for most of the session, and it
fades in instead of moving. It relaxes as the face falls asleep (0.3) and never
vanishes: a sleeper still has a face. Owner arbitration 2026-09-05 (D1).

### 3. ONE breath goes through the whole face

The first plan gave the brows and the mouth their own drift loops on their own
periods. That was three organs twitching on three timers. Instead the existing
breath — the two incommensurable sines on the mass — now carries the brows
(lift on the inhale, negative is up) and the mouth's width, on the **same
period** as the mass and a fraction of a turn behind it, the right brow behind
the left. Amplitudes derive from the family's own breathing depth, so a drowsy
face breathes shallower everywhere at once: 0.8 px of brow travel at the calm
depth and medium size, 1.2 px at the large one, and the liveliest family at
the largest size stays under the two-pixel line (first shipped at 0.4 px,
which read as static next to the eyes). The brows get **no drift of their
own**: a brow that wanders is a tremor. The mouth corners keep their slow
drift, doubled to cross the pixel (0.06 of curve, 0.09 of skew).

### 4. Secondary couplings live in the RIG, not in the sheet

Looking up lifts the brows and looking down relaxes them
(`BROW_GAZE_LIFT_EM = 0.03` per gaze unit); a blink drags each brow down with
ITS lid (`BROW_BLINK_DIP_EM = 0.03`), so the reopening rebound lifts it back
and the trailing right eye trails its brow too. Both are contributions on the
OUTPUT, like the arc: no spring, no channel, gone with their cause.

They could have been two `calc()` terms, and the first plan put them there.
They are not, for an engineer's reason rather than an animator's: a coupling
is motion, the boundary rule gives motion to the rig, and a constant inside a
`calc()` is a number nothing can read — invisible to every frame test and to
the bubble guard that has to know how high a brow can reach.

**The trap this opened is closed by construction.** The idle fast path only
rewrites the channels a loop rides. A coupling written as `output[key] += …`
would be added again on every quiet frame and drift, silently, for the whole
session. Every contribution in `writeDerived` is therefore written as an
ABSOLUTE value from the spring plus the loops' own offset, and a test compares
**twenty thousand 16 ms steps against one single step** of the same duration on
three resting states chosen for what their loops leave unridden (a breather, a
sleeper, a thinker): every published channel must agree to six decimals.

### 5. Beats reach the mouth, and the mouth has beats of its own

- the `brow` gesture now raises the BROW — height, arch and presence, one side
  — so the `wink` accent (ADR-253) is finally a raised eyebrow;
- three new idle gestures, awake families only: `lip-press` (width and curve
  pull in for a beat, "hm"), `corner-tug` (one corner flickers and the brow
  above it agrees a beat later) and `brow-twitch` (both brows lift and arch
  for a beat — something crossed the mind);
- **the eye beats carry the face** — owner feedback on the running widget
  (2026-09-05): the eyes played a beat every few seconds while the mouth and
  the brows only breathed. A `perk` now raises and arches the brows, a
  `squint` knits them and narrows the mouth, a `tilt` smirks with one corner
  and one brow. Coherence by construction: a secondary action rides the beat
  that causes it instead of a second random timer. About a third of every
  awake family's picks now reach the face (30 % `calm`, 40 % `lively`,
  pinned by the engine test), and the family weights still preserve the picks
  the widget tests pin (0 → saccade, 0.5 → glance, 0.6 → tilt, 0.7 → squint,
  0.9 and 0.95 → flicker on `calm`);
- **every beat is played at a size drawn for the occasion**: the host passes a
  scale in [0.85, 1.15] to `tapesForGesture`, which scales RELATIVE tapes only
  — an absolute closure (a lid at 1) is a fact, not an offset. The rig and its
  tests never draw (the default is exactly 1), and the widget tests pin
  `Math.random` at 0.5, which is a scale of exactly 1;
- a sigh (`slow-blink`) narrows the mouth on the exhale; a hop (`bounce`)
  drags the mouth along a beat late with follow-through;
- `thinking` CHEWS: the corners and the width work on two clocks (2.3 s,
  3.1 s), the one resting pose where the mouth is allowed to work;
- a sleeper breathes through a mouth that hangs open, on the eyes' own slow
  swell.

### 5bis. The mouth has a life of its own

The owner watched the running widget after §5 and said the mouth was still
far too static: "movements and mimics, at random, at a random frequency". He
was right, and the reason is structural. The moving hold is under two pixels
by rule; the idle gestures reach the mouth on a share of picks, and the ones
that do move its width or a corner — never its CURVE and never its OPENING,
which are the two things a viewer reads. Between two turns the mouth stayed a
bar under two living eyes.

So the face gets a **life of its own** (`rig/life.ts`). A first, discreet
version — eight small mouth-only mimics, soft springs — "moved a little" and
the owner called it neither Pixar nor expressive, which it was not: this
character is a CARTOON, a little funny, and it embodies LIA, not a face on a
video call. The library is therefore nine **mini-scenes** in which the whole
face commits: a big cheesy **grin** that squashes the eyes into happy arcs
and lifts the brows (with a tiny pull-in first — anticipation), a **gasp**
that drops the jaw to an O, widens the eyes, flings the brows and pops the
head, a **sulk** with the corners way down and the eyes' outer corners
drooping, a **hmm** with the lips pursed to one side, one eye narrowed, one
brow up and the head tipped, a **smirk** held with the other eye half shut,
a **pucker**, a **giggle** on two bounces of the head, a mouth **wiggle** and
a lip **smack**. Each is a RELATIVE performance (every tape returns to a
relative zero, none outlives 1.2 s) written as **attack, hold, release**: the
shape is reached inside 130 ms with a little overshoot, HELD 350 to 700 ms
so it is read, and let go slower than it came — a shape that is not held is
noise, which is the whole difference between a mimic and a tic. The big
scenes are drawn rarer than the small ones (46 % against 54 %: a face that
gasps every ten seconds is a slot machine), at a **random cadence**, at a
**random size** (0.8 to 1.2) and on a **random side**, on the resting
expressions only (the breathing set).

**The cadence and the release were calibrated a second time, on the owner's
eye.** The first cartoon version drew a scene every 2.2 to 6.5 s with
follow-ups at 0.9 s; added to the eye gestures the idle life already plays
every 1.9 to 5.6 s (a third of them reaching the face), the face did
something every two seconds and read as *nervous tics*. The standard for a
resting character is a facial beat every eight to twelve seconds with the
eyes wandering in between: the cadence is now **6 to 14 s** (a mean near
nine, three to nine scenes a minute, pinned over five simulated minutes),
the follow-up **10 %** at **1.8 s**. And the release is no longer a key:
the first version keyed the return on the attack spring, so every scene
snapped shut as fast as it had opened. A scene's tape now **ends at its
release** and the channel is handed back to the pose, which it reaches on
the **expression's own dynamics** — the `base` preset settles in about
650 ms, a drowsy face slower still — the slow-out of the textbooks,
continuous by construction since position and velocity carry across the
hand-over. Measured on a grin: 270 ms to the top of the smile, 250 ms to
1.1 s to come home, always longer than the way in. The attack springs
themselves were damped from 0.55 to 0.72: a ring on a face is a twitch. The rig schedules it on its own clock,
checks it before either step path, restarts it on every expression change so
a mimic never lands on an entrance, and keeps the mouth width above a floor
(`MOUTH_WIDTH_FLOOR`) so a pucker scaled up never draws a dot. The gaze,
the lids, the blink and the silhouette radii are never a mimic's: the gaze
aims, the lids state a fact, the radii are the style.

**A scene INKS what it moves.** The mouth and the brows rest at half
presence (a quiet face), and on the frozen strip a grin performed at half
ink read as washed out next to two solid eyes. Every scene therefore carries
its own presence tapes (`mouthA`, `browAL`, `browAR`) — full ink for the
big scenes, part of the way for the small ones — keyed on its lead mouth
tape's attack and release and lasting as long as its longest tape, so the
ink can never outlive or lag the shape it belongs to.

Two rules keep it honest, and the second is the engineering point:

- **it only exists with an entropy source.** `RigOptions.lifeRandom` is a
  separate stream from `random`: the widget tests pin `Math.random` with
  exact once-sequences read at mount in a known order, and a life drawing
  from that stream at construction shifted every one of them by one and
  failed four tests three files away — measured, not feared. The host seeds
  a tiny xorshift generator once per mount (`createLifeRandom`, salted so
  twelve style previews mounted in one millisecond do not mime in unison),
  and the gesture size of §5 now draws from the same stream, so nothing the
  rig does ever touches `Math.random` beyond the arrival pace it already
  drew. Every test builds rigs without a life, so the pixel budget of §8 is
  measured on the hold alone, which is what it is a budget for;
- **a mimic is a beat, not a hold**: the same tape mechanism as a blink, so
  it composes with the breath and the drift, is overridden by a reflex, and
  hands the channel back on its own.

Verified in the running application (dev container, `attentive`, large
size, sixty seconds). First, discreet version: 15 mimics at irregular
instants, the mouth height spanning 10.7 px where the hold spanned 1.4.
Cartoon library: 14 scenes, the mouth height spanning 14.9 px, the arc
reaching 1 (a full grin), the eye shapes squashing to 0.67 and widening to
1.21, the presence of the mouth and the brows rising to full ink on eight
scenes in forty-five seconds — and the eyes' own idle life untouched
(swap, bounce, tilt, brow-twitch, squint and brow all played meanwhile).
The nine scenes were also frozen at rest, attack, hold and release in the
hermetic harness and judged as stills.

### 5ter. Sketches — the little scenes

The owner asked, last, for something the face does "now and then, at
irregular and well-spaced intervals": three to five second scenes with
worked animation, funny, surprising, in the cartoon and Pixar spirit — a
catalogue of ten. A mimic is one beat, one thought; a SKETCH is a piece with
a beginning, a turn and an end, and it is what makes the avatar a character
rather than a status light.

`rig/sketches.ts` holds ten: **the fly** (the eyes chase it in zigzags,
the head follows, the brows knit, a big blink and it is gone, a satisfied
grin), **the double take** (a casual look left, away, then a SNAP back with
eyes wide and jaw down, held, then a sheepish smile), **the sneeze** (brows
climb and eyes squeeze while the mouth opens by degrees and the head draws
back, then the whole face squashes down eyes shut, and recovers with a
sniff), **the yawn and stretch** (enormous, slow, the face stretching
taller, a sleepy blink, a shake awake), **the hiccups** (three, never on
the beat, then the face surprised at itself, then embarrassed), **peekaboo**
(eyes shut tight over a mischievous grin, one eye peeks, both pop open —
boo), **dizzy** (the eyes roll around twice, the head wobbles half-lidded
with a wavy mouth, a shake clears it), **the doze and snap** (the eyes droop
by degrees, the head tips, the mouth slackens, then a jolt, a dart left and
right, a sheepish grin), **the brow groove** (the brows take turns to an
off-beat head bob and a mouth wiggle, ending on both brows up and a grin)
and **suspicious** (narrowed eyes slide slowly left then right, one brow up,
the mouth pursed aside, then "nah": brows up, a grin, a blink).

Mechanically a sketch is one thing the rig already knew how to play: a set
of tapes whose keys span the whole scene, on every channel the rig owns —
the gaze, absolute, because the scene decides where the eyes look (the
catch-lights sent the same way), the blinks, the eye shapes, the mass, the
head, the brows, the mouth and the ink. It has its own list in the runtime,
ranked between the one-shot beats and the state's patterns: a spontaneous
blink or a host gesture still wins over it, and it wins over a search. Four
rules, each a test:

- **a scene is a piece, not a beat**: three to five seconds, on the
  channels the rig owns and never on the lids or the silhouette (a relative
  lid tape on a style that folds its lids into a squash would clip a ring —
  the ADR-252 trap; closing is a blink, narrowing is a squash), and the face
  is EXACTLY where it was when the curtain falls — a twin rig without the
  scene, stepped the same time, breath and drift included, agrees within a
  hundredth on every channel 1.6 s after the longest tape;
- **rare, and only on a resting face**: 45 to 120 s apart from the same
  entropy stream as the mouth's life (four to fourteen scenes over ten
  resting minutes, never two closer than the floor, no two gaps alike),
  never on a thought in progress, a reaction, a search, a sleep or a speech;
- **one thing at a time**: the mouth's own life stands aside for the scene
  and a breath after it, and a second scene replaces the first rather than
  stacking on it;
- **a scene never outlives its state**: the next expression change drops it
  on the spot, and the channels ease home on the arrival's own dynamics.

Two floors came out of the scenes and the mimics together, both on the
OUTPUT and both documented in `runtime.ts`: the mouth width never draws
under a fifth of the style span (a pucker scaled up on a narrow mouth is a
small mouth, never a dot), and an eye is never squashed under a tenth by a
beat — a grin on a pose that is already a dome (joy squashes to 0.55) would
otherwise close it past a sliver, while a tenth is the closed happy eye of
the cartoons and stays under the deepest folded lid a squash style draws.

The choreography vocabulary the scenes needed — a relative beat that ends at
its release, an absolute one, the same beat on both sides with the right one
trailing and a hair smaller, a mirrored pair, a scaler that spares absolute
closures — was written four times across the arrivals, the gestures, the
mimics and now the sketches, and the trail and the jitter had started to
drift between files. It is one module now (`rig/choreo.ts`), and the four
import it.

### 6. Speech has phrases, and brows

A slow `hold` envelope on `mouthOpen` (3.7 s, held at its ends) drives the
flap THROUGH the closure for a few hundred milliseconds between two runs of
talk, and a second, slower sine (5.3 s) keeps the pauses off any beat. The rig
bounds the opening in [0, 1], because the envelope deliberately crosses zero
and a negative opening would shrink the bar under its own ink. Measured over
twenty seconds: the mouth is closed **9.6 %** of the time, in runs of at
least 96 ms, and opens to 0.46 at most.

The brows punctuate: a looping pattern (the mechanism of the search saccades)
raises both brows on four beats per 5.2 s cycle, no two the same distance
apart, each held about a syllable, the right one trailing by 40 ms. A pattern
keeps the rig on full frames, so this was **measured** in the hermetic harness
rather than assumed: 60 frames per second for the duration of a speaking turn,
**0.11 ms mean, 0.3 ms worst** per frame for the rig and its DOM write.

### 7. Entrances, extended to the organs

Surprise flings the arch past its pose before anything else has moved (0.90
at 80 ms, 0.85 settled); joy and excitement pop the arch with the smile;
tenderness swells it; the one raised brow of a question overshoots while the
other stays put; the brows of sadness sink LAST, after the mass and the frown;
and tiredness arrives on a **yawn** — the mouth opens to 0.53 and closes on
its own weight inside the entrance, the pose itself keeping a closed mouth.

### 8. A budget, in pixels, in the tests

"Alive, not agitated" is a number. `rig/__tests__/life.test.ts` runs one idle
minute for eight resting states at the three widget sizes and converts the
channels through the stylesheet's own arithmetic (`__tests__/screen.ts`): the
mouth must move by at least 0.6 px and by at most 2 px in height and width at
the medium size; the brows must breathe by more than 0.1 px and less than 2 px
at every size; a thinking mouth may work up to 3 px; a concentrating face
moves by exactly 0. The bubble guard now measures the brow's reach at the
LOUDEST the face can be (the widest register amplitude times the liveliest
family, arch included) and the bubble rose from 1.05 to 1.25 of its own em:
clearance **0.206 em, 6.2 px at the medium size**, where the previous guard
had measured the pose as authored.

### 9. Two small corrections found on the way

The mouth's bottom vertical radius was a fixed 100 %: CSS normalises the pair
to 33 %/67 % at the flat crossing (computed, not guessed) and the mirror
between smile and frown visibly swapped the rounder end of a 3 px bar. It now
follows the arc — 50 %/50 % at the crossing, the same 9 %/91 % at a full grin.
And the `resolveLoops` amplitude a mouth test tolerated was hard-coded
(`0.03`); it is read from the loops now.

## Consequences

- Two channels more (57 → 59). The rig's cost is unchanged in kind
  (1.66 µs per frame measured before, sub-millisecond with the DOM write
  after). The four long-clock widget tests (fifteen simulated minutes each)
  measure 3.4 to 4.0 s isolated under coverage instrumentation, against 2.8
  to 3.2 s before — the price of two channels and two brow riders on every
  idle frame — and keep their 40 s budget untouched.
- Coverage of `src/components/eyes/**` measured 94.80 / 88.63 / 96.56 / 96.84
  after the change; the 93 / 86 / 95 / 95 floors hold and cannot be raised by
  the two-point rule. The global floors are unchanged (78.46 / 73.76 / 75.65 /
  79.20 measured, 76 / 71 / 73 / 77 held).
- The `speaking` state runs at full frame rate instead of the idle cadence,
  measured above. If a future measurement disagrees, the fallback is loops
  with a `hold` waveform, which keep the idle cadence.
- `traits` has no brow (`--has-brow: 0`) and is untouched by design: the
  stroke IS the brow there.
- The face's own life is a SWITCH the host declares (`life` on
  `ExpressiveEyes`, `data-life="off"` on the root when off). The twelve
  previews of the style picker turn it off: a preview is there to compare
  silhouettes, and a sneeze mid-comparison is not a comparison. The breath
  and the moving hold stay on a preview — they are the pose, not a beat.
  Found by the cold review, not by a test: the previews mount the same hook
  as the widget and had inherited the mimics and the sketches with it.
- Verified in a browser, hermetically (the real rig, the real stylesheet, the
  exact markup, no app): the matrix of twenty expressions by six styles, and
  frozen frames of a blink at 96 ms (left brow down 1.13 px, right 0.33 px —
  it trails), a brow flash, the surprise overshoot, the yawn, two speech
  frames, the chew, the lip press and the corner tug.

## Rejected

- **Brows absent at rest, animated only through beats.** Would have kept the
  ADR-252 silhouette, and left the breath and the two couplings inert ten
  moods out of fourteen.
- **Couplings in the stylesheet.** Zero rig cost, and the arguments of §4.
- **Independent drift loops on the brows.** Noise correlated to nothing;
  replaced by the shared breath (§3).
- **A brow rotation drift.** ±0.7° of wander on a brow reads as a tremor.
- **Exaggerating the mouth opening with the register amplitude.** A
  `surprise` at 1.8 would open to 1.35 and the bar would be taller than the
  eyes; the jaw drop stays the pose's own.

## Related

- ADR-252 (the rig and its boundary rule — amended here on the resting brow),
  ADR-253 (the tone accents that now reach a real brow), ADR-240 (the widget;
  its §5 mounts the same face on the public landing, where all of this life
  plays on a resting expression).
- The `/more` page presents this life as its own card (`living_face`, section
  02), one level below the capability cards; `docs/technical/LANDING_PAGE.md`
  describes the landing mount.

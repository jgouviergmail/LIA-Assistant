# ADR-252 — A transition is not a performance: the expressive-eyes animation rig

- **Status**: Accepted
- **Date**: 2026-08-31
- **Related**: ADR-240 (expressive eyes widget), ADR-243 (OLED depth),
  ADR-146 (reduced motion), the twelve principles of animation
  (Thomas & Johnston, *The Illusion of Life*)

## Context

The eyes widget (ADR-240) had grown a serious CSS animation system: twenty
expression recipes, six selectable styles, an idle-life gesture library,
masking blinks, per-emotion arrival durations. It was carefully built, and it
had reached a ceiling that no amount of retuning could lift, because the
ceiling was **structural**.

**Every state change was a CSS `transition` between two static poses.** A
transition interpolates in a straight line through property space. That single
fact rules out, by construction:

- **anticipation** — no counter-move can precede the action;
- **arcs** — the gaze travelled on a rail (one `translate`, one timing
  function);
- **overlapping action** — lids, mass and silhouette all departed on the same
  frame, on the same curve;
- **velocity-driven squash & stretch** — the only squash available was frozen
  in keyframes;
- **continuity through interruption** — a transition cut mid-flight restarts
  from wherever the interpolation happened to be, dropping its velocity. This
  is the one a viewer feels without being able to name it: changing emotion
  mid-move looked like a UI cutting a transition, not like a creature changing
  its mind.

A second ceiling was the **matter**: a flat fill plus a halo. No volume, no
cornea, no catch-light parallax — the strongest available cue that a shape is
a shape rather than a thing.

A third was **vocabulary**: the "brow" was the eye's own slant, and there was
no pupil outside one style's decorative dot. The two organs that carry most of
a face's expression did not exist.

## Decision

### 1. TypeScript owns what MOVES; CSS owns what is DRAWN

A rig (`components/eyes/rig/`) computes the motion and publishes it as
`--rig-*` custom properties on the eyes root, every frame. The stylesheet
consumes those properties and keeps everything else: silhouette geometry,
skin, matter, the identity of the six styles.

The boundary is a single greppable rule, and therefore guardable:

> A stylesheet **reads** `--rig-*`; it never **declares** one, and it never
> puts a `transition` on a property the rig writes.

`rig/__tests__/css-boundary.test.ts` enforces all of it, plus two things a
comment could not: every `--rig-*` the sheet reads is a real channel, and every
`var(--rig-x, fallback)` fallback still equals that channel's declared rest
value. Those fallbacks are what render the neutral pose before the first frame,
and drift there would be invisible until someone loaded the page with JS off.

The DOM carries two vocabularies, and the distinction is the architecture:
`data-*` is the **state** the host declares (expression, style, mood family,
gesture, blink, gaze aim); `--rig-*` is the **motion** the rig computes.

### 2. Three mechanisms, composed — never in competition

Per channel, every frame:

```
target = one-shot beat  >  state pattern  >  gaze aim  >  expression pose
value  = spring(target) + loops
```

- **Springs** give arrival its physics. Analytic (the closed-form damped
  oscillator), not integrated: a background tab hands the loop a delta measured
  in seconds, and a numerical integrator explodes there. Exact at any `dt`,
  frame-rate independent, and — the point — **velocity survives a retarget**.
- **Tapes** are short timed sequences of targets on one channel. One mechanism
  now covers what used to be four: anticipation, the blink, one-shot beats, and
  scripted arrivals. Keys are held, not interpolated, so the spring between two
  keys draws the curve — which is what turns a two-key tape into a real
  anticipation arc rather than a linear ramp.
- **Loops** are additive oscillators for the motion that never arrives
  (breath, shiver, drift). They had to leave CSS: a `@keyframes` *replaces* the
  property it animates, so a loop and a pose could never share a transform.

This composition is the whole reason the previous system could not do these
things at once.

### 3. The animation principles are mechanisms, not adjectives

| Principle | Mechanism |
|---|---|
| Timing & spacing | a spring preset per emotion, derived from the durations it replaces (`f = 1.057 / t99`) |
| Anticipation | a counter-move tape on the willed channels — **skipped for reflexes**, because a startle that telegraphs itself is not a startle |
| Overlapping action | the gaze leads, the mass follows, the lids trail; departures are staggered by group as well as arrivals |
| Arcs | a vertical bias proportional to horizontal speed — zero at both ends, greatest mid-travel |
| Squash & stretch | derived from the springs' own velocity, at constant volume, along the direction of travel |
| Moving hold | two incommensurable sines per gaze axis: a settled face never freezes |
| Secondary action | the pupil is its own group, and it moves a beat **after** the face |
| Exaggeration | the mood family scales amplitude and pace — of the pose and the mass only |

Exaggeration deliberately does **not** touch lids, blink or radii: those state
a fact rather than an intensity. A drowsy `sleep` scaled to 92 % is a character
sleeping with its eyes 8 % open — caught by a test, not by reading.

### 4. Two organs, opt-in per style

The **brow** is a real element with its own height, tilt and presence, sitting
outside the lid layer (a blink must not clip a brow). It is **invisible on a
neutral face**: it appears only when it has something to say, so no style pays
for it at rest while every style that wants one gets the most legible emotional
cue a face owns. Lowered inner ends scowl; raised ones grieve — a grammar the
tests enforce across all twenty expressions rather than trusting twenty
hand-written recipes.

The **pupil** sits inside the shape, so the lids cover it like everything else,
and travels *further* than the eye does — that difference is what reads as
looking around inside the eye rather than moving the whole head.

Both are gated on style tokens (`--has-brow`, `--has-pupil`), never on a
hard-coded list of style names: a stroke language has no room for a second
stroke above the first, and a solid glowing screen has no inside.

### 4bis. A mouth, and a bubble that clears the face

The mouth was added after the first pass, and it changed the anatomy: two eyes
with brows are a pair of eyes; add a mouth and it is a face. Three decisions
carry it.

**One signed curve, not two shapes.** A smile and a frown are the same shape
and a sign. `mouthCurve` is signed, and the rig hands the stylesheet a positive
DEPTH plus a DIRECTION — because CSS can express neither an absolute value nor
a sign. A box of zero height still paints its bottom border, so a flat mouth is
a straight line and the arc grows continuously out of it: the spring travels
from grief to delight through a line, instead of cutting between two drawings.
The direction is HELD through that crossing, exactly like the stretch axis, or
a mouth resting near zero would flicker on numerical noise.

**It is never absent.** The brow may be — a calm face has no marked brows — but
a face that GROWS a mouth in order to smile is a face with a defect. It is
quiet at rest instead: a short line, barely curved upward, because a dead
straight one under two eyes reads as stern.

**The acting lives in the CORNERS.** A mouth that can only be symmetric
plays happy and unhappy and nothing else. `mouthSkew` lifts one corner and
drops the other, and it is what makes a wink crooked, a question quizzical,
a thought chewed and boredom slack. It is multiplied by the direction before
it reaches the drawing: the shape is mirrored for a frown, so a bare
rotation would swap the raised corner exactly at the flat crossing, where
the tilt is the only thing left to see.

**It is a SOLID SHAPE, not a stroke.** The first version drew lips: a thin
arc, an outlined opening and a tongue, three elements kept in step by hand.
Under two filled, glowing eyes that is a line drawing wearing a screen face —
and the reference language for this character (Cozmo, Eilik, the whole family
of screen robots) draws every feature as a filled silhouette. One element
carries the entire vocabulary instead: the HEIGHT grows with the curve and
with the opening, so a resting bar, a deep grin and a gasp are one shape at
three sizes; the TOP EDGE flattens as the curve deepens, because a
flat-topped, round-bottomed slab *is* a cartoon smile while the same shape
uncurved is a rounded little bar; and `scale: 1 -1` turns the whole thing over
for a frown, so the two are one drawing the spring can travel between.

This is why `mouthArc` is published UNITLESS. The stylesheet needs the depth
as a height AND as a corner-radius ratio, and CSS cannot divide a length by a
length — in em it could have been the first and never the second.

Mirroring costs one correction, and it was found in a browser rather than
read: turning the shape about its top edge sends a frown growing *upwards*,
into the face. Measured before the fix, every flipped mouth overlapped the
eyes by 3.2 to 7.7 px at all three sizes while every unflipped one cleared
them by 5.5 to 13.8. Translating the shape down by its own height when — and
only when — it is flipped puts both directions in the same band; the same
measurement then reads 4.3 to 13.8 px, positive throughout. A unit guard holds
the term in place.

**Every emotion makes its mouth ARRIVE.** A smile snaps past its curve and
settles back into it, a startle drops the jaw past the open pose, anger
pulls the mouth in tight before it sets, and a frown deepens *after* the
eyes have fallen — grief is sequential, and a face where everything lands on
one frame is a mask being swapped.

**`speaking` finally speaks.** It used to be a bob of the eyes. The mouth now
flaps on two incommensurable components (~260 ms, roughly a syllable, plus a
longer one), and widens as much as it opens. One sine would have been a
metronome.

The floating emote became a **comic speech bubble** at the same time, and for a
reason the brows created: the space just above the eyes used to be empty, so a
bare glyph sat comfortably 0.08em up. Once brows existed, that glyph sat *in
them*. A bubble fixes both halves — it clears the face by its own height, and
it reads as an object the character is thinking rather than a mark floating
inside its expression. The clearance is computed from the stylesheet and the
pose table in a guard, not eyeballed once; measured in a browser, the tail's
point sits 28.3 px above the highest brow.

### 4ter. How hard a reaction lands, read from the answer

`deriveReaction` decides WHICH expression a completed turn earns.
`responseEmphasis` decides with what FORCE it lands, and it is deliberately
a separate function with a separate input.

**It never asks the psyche.** The psyche models what LIA feels; it is not an
animation input, and stretching it into one would make a model of an inner
life answerable for a punctuation mark. The emphasis is read from the
delivered text alone — which is public by definition: exclamation marks,
celebratory emoji and shouting push it up; an ellipsis, a code block or a
long expository answer pull it down. Punctuation inside a code fence does
not count, because `print("!!!")` is not enthusiasm.

The result multiplies the pose exaggeration (and, at half strength, the
arrival pace), so the SAME emotion arrives bigger after "Terminé !" than
after three screens of technical explanation. It scales an expression; it
never picks one, and it is bounded to [0.75, 1.4] so a face can be insistent
without becoming a caricature. It also expires with the reaction it belongs
to — an emphasis outliving its answer would colour unrelated expressions.

### 5. Matter, dosed per style

One light source and a surface falling away from it, a rim light and a contact
occlusion (both **inset**, so the lid clip carries them — an outer shadow once
streaked a squashed smear across the silhouette on every blink), and **two**
catch-lights moving by different amounts. That ratio is the cornea: equalise
them and the eye goes flat again. They chase the gaze on a slow spring, so they
arrive late and drift past on the way back — a reflection belongs to the room,
not to the eye.

`--matter` and `--gloss` are plain multipliers, so a style turns the whole
treatment off with a zero. `traits` and `anneaux` do exactly that: a stroke and
an outline have no surface, and lighting them would destroy what they exist for.

### 6. A search is saccadic, and an emotion has an entrance

Two decisions that came from watching the result rather than from the plan:

**A smooth left-right sweep is a security camera.** Eyes looking for something
make saccades — a jump, a brief fixation, another jump, to scattered places,
never on a beat. `searching` is now a looping scripted pattern of eight
irregular fixations. The measurement that separates the two: peak frame-to-frame
movement over its median is **> 6** for the pattern, where a sine sits near 1.5.

**Springs alone give every emotion the same choreography.** Anger now takes a
breath and slams, fear recoils, sadness only ever deflates, a question tips its
head. Each is a handful of keys, and it is the difference between an interface
changing state and a character reacting. Arrival *pace* also varies slightly per
performance, from an entropy source the React binding passes and tests omit — so
the rig stays perfectly deterministic under test while two angers are never
quite the same on screen.

## Consequences

### What this buys

Motion became **testable for the first time**. The previous system could only
be tested for the state it declared; the clock is now an argument, so every
principle above is asserted frame by frame — the anticipation overshoot, the
blink's rebound past open, the arc on a purely horizontal gaze, the pupil that
has not moved while the face already has.

### What it costs, and what was done about it

A permanently visible widget now runs a JS animation loop. Three measures keep
that honest:

- **one shared frame clock** for every rig on the page (the widget plus the
  twelve style previews) — one request, one delta, one timeline;
- **the loop stops itself** when nothing is moving;
- **an idle cadence**: when only the perpetual loops are running, the clock
  samples at ~30 Hz instead of 60. Breath is a multi-second cycle, so a third
  of the frames samples it indistinguishably. Measured on the widget's own
  long-clock tests: 3.08 s → 1.42 s for fifteen simulated minutes.

Measured per frame, the rig itself costs ~3.5 µs; the DOM write dominates, and
a settled channel writes nothing at all (a value that cannot change its own
displayed text is never even formatted).

Four more reductions came from the mouth, which took the channel count past
fifty and put the widget's long-clock tests over their budget under coverage
instrumentation — a useful alarm rather than a nuisance. **Loops are added by
walking the loops, not the channels** (a handful are ridden, fifty are not); a
**pure-idle fast path** updates only those ridden channels when every spring has
arrived and nothing is playing; the **settling check runs once per frame**
instead of twice; and the **write precision** of the drifting channels went from
four decimals to three, which is 0.006 px of travel and halves the idle writes.
None of them changes what is drawn.

What remains is inherent, and is stated where it costs: four tests simulate a
quarter of an hour — roughly 27 000 animation frames — and carry an explicit
40 s budget measured at 2.8-3.2 s each under coverage in isolation, against a
~5x stretch in the full parallel run. The global 15 s default is untouched, so
it still catches a genuinely hung test.

### Reduced motion

The rig snaps every channel onto its pose, runs no loop, plays no beat and
never asks for a frame. Accessories are declined outright — a flourish is the
first thing that preference asks to be spared.

### Evidence

Verified in a browser, hermetically (the rig and the real stylesheet, no app,
no session): the full 20 × 6 matrix in both themes, and frozen frames of the
blink, the anticipation, the arc and the search path.

That proof caught two defects no unit test would have: with `focused`, the
sustained lid clip rendered `traits` as two specks and `anneaux` as two
disconnected side arcs. The blink already had a squash exception for those two
languages; the sustained lids never did. Closing it is `STYLE_LID_MODE`, and a
guard now checks that the rig and the stylesheet agree on which styles squash.

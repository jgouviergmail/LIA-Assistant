# Living limbs for LIA's animated companions

**Date:** 2026-11-07
**Status:** Accepted and implemented locally on 2026-11-07; final qualification is recorded in the [implementation plan](../plans/2026-11-07-avatar-limb-animation.md).
**Scope:** Native animated companions, resting and contextual limb motion, and
bounded material refinement.

## Intent

The owner wants LIA's animated avatars to feel more alive through their arms,
hands and legs, both at rest and in context. Facial animation and whole-body
acting already exist. The work should strengthen the character's presence and
make its appearance pleasant without constant distracting motion.

Natural, restrained acting within the existing stylized identities is the
accepted direction. Engagement and attachment
are intended benefits, not outcomes established by an animation test.

## Findings before implementation

- The [companion catalogue](../../../apps/web/src/components/spirit/companion-catalogue.ts)
  selects reviewed frontal body artwork for each identity and variant.
- [Native volume](../../technical/NATIVE_AVATAR_VOLUME.md) uses that image on an
  alpha-derived relief. There are no separately authored limbs or articulated
  fingers. Hidden anatomy is approximate, as stated in
  [ADR-340](../../architecture/ADR-340-Native-Avatar-Volume-From-Reviewed-Offline-Art.md).
- The [channel table](../../../apps/web/src/components/eyes/rig/channels.ts)
  originally had whole-body transforms but no joint channels. The
  [body scenes](../../../apps/web/src/components/eyes/rig/body-sketches.ts)
  translate, turn and stretch the complete character.
- The [GPU renderer](../../../apps/web/src/components/eyes/volume/mesh-gpu.ts)
  originally turned the entire mesh together. Its
  [binding](../../../apps/web/src/components/eyes/volume/volume-binding.ts)
  skipped redraws when its observed pose/material values were unchanged.
- The [fringe](../../../apps/web/src/components/eyes/volume/volume-fringe.ts)
  contains soft and unmeshed source detail on a separate planar surface. It must
  follow any local articulation or an unmoving duplicate can remain visible.

The current body images were visually inspected. Their anatomy differs enough
that one universal human skeleton would distort several identities.

## Visible behavior

| Situation             | Accepted acting                                                                                                                                        |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Quiet presence        | Small asymmetric arm relaxation; occasional wrist settling and weight transfer where feet exist. Motion shares the current breath and resting cadence. |
| Listening / attentive | A more settled stance and restrained arm opening, with gentle return to rest.                                                                          |
| Thinking / searching  | Small one-sided hand or forearm adjustment; feet remain mostly settled. No repeated pretend typing or unearned action gesture.                         |
| Speaking              | A few arm and wrist accents tied to the existing generated speech phrases; release during pauses, rather than a wave on every syllable.                |
| Emotion / reaction    | Existing expression and intensity influence openness and energy. A visual gesture does not imply a completed tool action.                              |
| Existing body scenes  | Limbs anticipate and follow jumps, bows, surprise and dance where anatomy permits. Existing scene timing remains authoritative.                        |

Movements have an anticipation, a readable hold and a slower release. Mirroring,
amplitude and timing may vary using the rig's existing seeded entropy. No limb
owns a new random timer. A state transition interrupts the previous acting and
retains continuous spring position/velocity on release.

The anatomy mapping is explicit:

| Identity                         | Articulation scope                                                                                                                     |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| BIP, Boulon                      | Short mechanical arms/hands and feet; compact joint movement, limited casing deformation.                                              |
| Oscar                            | Upper arms, forearms, wrists and legs/feet where visible; conservative bends around clothing.                                          |
| Moss, Lumen                      | Small side appendages and visible feet; soft attachment falloff.                                                                       |
| Spirit                           | Visible side appendages; no invented legs where the artwork shows none.                                                                |
| Nimbo                            | Visible lateral lobes only, without deforming the central face; no invented legs.                                                      |
| Orbit                            | No limb articulation: inspection confirmed a continuous ring, which remains intact. Existing facial and whole-body acting is retained. |
| Monitor, Smiley, eye-only styles | No added limbs. Preserve their existing native expression and whole-body acting.                                                       |

Both variants require separate visual calibration. Hands articulate as drawn
units at the wrist or end of the arm. Independent fingers, gripping objects,
large hand-over-face poses and unrestricted body turns require new source art
and are outside this proposal.

The later owner correction retired Smiley from this original scope and requested
another scarf-fitting pass; the current execution and acceptance record is in
the [implementation plan](../plans/2026-11-07-avatar-limb-animation.md#owner-correction--2026-11-08).

## Implementation direction

Extend the existing TypeScript rig and native WebGL renderer. No new runtime
dependency, model call, backend service, preference or independent frame loop
is required by this design.

1. Declare anatomical pivots, influence regions, supported joints and motion
   bounds per identity/variant. Unsupported joints have an explicit zero
   influence rather than an inferred anatomy.
2. Prepare articulation data with the source geometry once. Keep original UVs
   and the reviewed art. Local bends must preserve attachment continuity and
   leave the face, core torso and collar landmarks invariant.
3. Apply the same deformation to physical front/rear geometry and fringe
   detail. The current single fringe quad cannot represent local bends:
   tessellate it into a bounded grid or use another equally coherent local
   projection, verified against the source alpha.
4. Deform normals consistently with positions. Retain material sentinels used
   to distinguish fringe/casing from geometric normals.
5. Add joint channels through the native channel vocabulary and use its existing
   spring/tape mechanisms. Compose idle, contextual and scene motion in one
   module with an explicit priority; avoid independent competing writers.
6. Include articulation in GPU redraw invalidation. A limb-only change must
   actually reach the screen even when the head and lighting are still.
7. Keep existing visibility, static portrait, reduced-motion, context loss and
   teardown gates. CPU data may be retained for resume; GPU ownership stays
   with the current binding.

[ADR-264](../../architecture/ADR-264-Living-Brows-And-Mouth.md) and
[ADR-294](../../architecture/ADR-294-A-Face-That-Never-Plays-The-Same-Twice.md)
remain the motion contract: one clock, absolute derived contributions, bounded
moving holds and scenes that do not outlive their context. Preserve the landing
page's existing wake policy and the user's saved widget position.

The builder chooses the exact channel names, joint count, data layout, spring
parameters and measured amplitudes. These choices must satisfy the observable
acceptance criteria rather than a copied numeric animation recipe. Existing
`body*` prefix behavior in the runtime must be reviewed before naming channels.

## Material refinement

The optional second pass improves the perceived material through restrained,
identity-specific response to the existing light: softer organic surfaces and
controlled highlights for mechanical bodies. Preserve original hues, alpha
edges, frontal identity and the current texture/buffer budgets unless a measured
change justifies a separate decision.

Do not apply blanket sharpening or saturation. The source art already contains
highlights and shadows; new light must not double them or wash out the face.
Keep a material change only if a side-by-side browser comparison shows a gain
at actual widget sizes in light and dark themes. If no improvement survives that
comparison, retain the existing material and report that result.

This pass does not claim to add missing texture detail. Higher-definition art
would be separately versioned and reviewed, following the catalogue's immutable
asset contract.

## Acceptance and qualification

- At least one visible arm/hand displacement occurs independently of the head
  in resting observation on identities with such anatomy; foot movement is
  independently visible where feet exist. Do not satisfy this with a root sway.
- Listening, thinking and speech produce distinguishable, restrained behavior.
  Speech gestures respect phrase pauses. Returns and interruptions do not snap.
- Across both variants, joints remain attached, the central face/collar stays
  registered, and no frozen fringe, double limb, hole or stretched ring appears.
- The undeformed pose agrees with the existing body. Repeated simulation does
  not accumulate drift. Angles and the painted envelope stay bounded.
- Invisible, reduced-motion and historical/static views do not animate limbs;
  reduced motion also prevents extra GPU work through the existing gates.
- Failed graphics setup and context loss retain the original readable avatar.
  Resume, replacement and unmount do not leak resources or preserve a stale pose.
- Check actual compact and large widget sizes, mobile/desktop viewports and both
  themes. Painted appendages must fit the existing viewport-constrained envelope;
  DOM bounds alone do not prove that deformed pixels remain visible.

Geometry tests should use independent landmarks and alpha observations, including
pivot invariance, untouched head/torso, attachment continuity, bounds, and matching
physical/fringe deformation. Runtime tests cover context/phrase alignment,
interruption, seeded variability and long-run stability. GPU tests cover
limb-only invalidation and all existing lifetime gates.

Extend the existing
[browser projection fixture](../../../apps/web/e2e/fixtures/volume-projection.ts)
and [companion journeys](../../../apps/web/e2e/smoke/spirit-avatar.spec.ts), using
controlled context and time. Record short before/after sequences as visual
evidence; a mocked shader or a changing channel does not prove good animation.
Sample frame cost and report the browser/device actually exercised, without
claiming unmeasured mobile-GPU support.

Implementation completion requires `task lint`, `task test:frontend`, frontend
coverage and relevant hermetic browser journeys on the current snapshot. Record
commands, exit status, counts, warnings and any unrelated blocking failures. No
Git mutation, commit, push or deployment is part of this work.

Update ADR-340 and the native volume/Spirit guides with the actual shipped
behavior and remaining limitations. The [execution record](../plans/2026-11-07-avatar-limb-animation.md#execution-record)
records the implemented behavior, verification results and material limits.

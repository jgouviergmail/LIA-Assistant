# Avatar limb animation implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the independent motion and renderer tasks, then review their integration. The owner requested complete execution without further approval gates. No Git operations.

**Goal:** Give every drawn companion limb visible, coherent resting and contextual motion, verified in the real renderer across both variants.

**Architecture:** Extend the existing rig's channels and tapes. Prepare per-identity anatomical influence data once, then articulate the original textured mesh and its fine alpha fringe together on the GPU. Retain the native lifecycle and facial projection.

**Tech stack:** Existing TypeScript, React, native WebGL, Vitest and Playwright.

**Spec:** [Accepted design](../specs/2026-11-07-avatar-limb-animation-design.md).

## Global constraints

- One rig clock; no additional animation timer or model call.
- Preserve art, facial animation, visibility/reduced-motion and fallback contracts.
- No invented anatomy, independent fingers or unsupported large occluding gestures.
- Calibrate every supported identity and both variants in the browser.
- Preserve concurrent changes; no Git mutation or deployment.

## Review focus

1. A stationary head must not suppress a limb-only GPU redraw (binding test).
2. Fine alpha detail must follow its limb without a stationary ghost (geometry and raster checks).
3. Changing state mid-gesture must preserve continuity and release the old gesture (rig test).
4. Small appendages must visibly move without pulling a face, torso or ring (anatomy tests and visual matrix).
5. Hidden/reduced-motion/context-lost views must stop rendering and resume cleanly (binding/browser tests).

## Task 1 — Native limb vocabulary and acting

**Own:** `apps/web/src/components/eyes/rig/` and its tests.

**Interface:** `armL`, `armR`, `wristL`, `wristR`, `legL`, `legR`, `footL`, `footR` are signed screen-plane degrees, zero at the authored pose. Positive rotation is clockwise in screen coordinates; left opening is positive and right opening negative. Export the canonical `LIMB_CHANNELS` list for the renderer and boundary guard.

- [x] Add behavioral tests for resting travel, listening/thinking/speech, phrase pauses, scene participation, interruption, reduced motion and drift.
- [x] Observe focused failures, then implement bounded limb motion through native spring/tape/loop seams and character capability checks.
- [x] Keep no-limb styles at zero, preserve native speech cadence and entropy ownership, and account for GPU readers in the channel-boundary guard.
- [x] Run the rig suites and inspect integration with the renderer's channel names.

## Task 2 — Anatomical GPU articulation

**Own:** `apps/web/src/components/eyes/volume/` and its tests.

**Interface:** Read Task 1's signed-degree channels. A typed profile declares limb pivots, local influence, distal joints and limits per character/variant. The neutral pose is identity.

- [x] Add independent geometry tests for untouched face/torso, fixed pivots, bounded joints, contour/fringe agreement and all anatomy profiles.
- [x] Observe failures, prepare skin data once, and articulate positions/normals through the GPU port without new per-frame geometry allocation.
- [x] Subdivide the fringe to follow local deformation, retaining material sentinels and UVs.
- [x] Include limb inputs in redraw invalidation; test limb-only redraw, allocation failures, loss/restore, reduced motion and cleanup.
- [x] Run geometry and binding suites. Retain source textures and drawing resolution; measured static skin/fringe memory growth is justified by keeping fine alpha detail attached.

## Task 3 — Browser qualification and material assessment

**Own:** Browser capture/test support and coordinated integration fixes.

- [x] Use a local browser surface loading real native components, rig and current renderer, without replacement animation.
- [x] Capture all companions and both variants at rest, attentive, thinking, speaking and representative body scenes, including light/dark and compact/large views.
- [x] Inspect every sequence for attached limbs, fixed central anatomy, coherent alpha detail and visible independent movement; correct calibration.
- [x] Exercise dynamic reduced motion and viewport containment in hermetic browser coverage.
- [x] Assess the material beside the original at actual sizes: retain the source texture and material, with lighting normals following articulation. Do not invent texture detail or double baked highlights.

## Task 4 — Integration review and repository gates

- [x] Independently review motion and renderer changes, then their cross-boundary behavior; resolve findings.
- [x] Run repository static gates, the full frontend suite with coverage and relevant browser tests, recording current counts, warnings and failures.
- [x] Update ADR-340 and native avatar guides with shipped behavior, evidence and limits.
- [x] Re-run affected checks after fixes; report the limb milestone without claiming unmeasured device performance. The separately commissioned artistic iteration below remains in progress.

## Execution record

- Owner approved complete implementation, tests and visual checks on every applicable avatar/variant.
- Ruling: proceed directly; the owner's explicit instruction supersedes intermediate skill approval requests.

### Implemented behavior

The rig now owns eight limb channels through its existing clock, springs and
scene tapes. Resting beats share facial-life scheduling; speaking accents follow
generated phrases and release during pauses. The GPU reads the same canonical
channel vocabulary, clamps joints by identity and variant, and redraws for a
limb-only change. Deformed normals use the spatial Jacobian; the fine alpha fringe
follows the same local skin as the body. Dynamic reduced-motion resume was corrected
to wake the existing rig cleanly.

Spirit and Nimbo articulate their lateral appendages; Moss and Lumen also move
their feet. BIP, Boulon and Oscar have arm, wrist, leg and foot articulation.
Orbit's continuous ring has no limb influence. Both variants were calibrated
separately. Original reviewed textures and material settings were retained after
comparison; lighting follows the moving surfaces without adding baked highlights.

### Current verification evidence

- Focused volume/component suite: `pnpm exec vitest run src/components/eyes/volume/__tests__ src/components/eyes/__tests__/BodyVolume.test.tsx src/components/eyes/__tests__/EyesFace.volume.test.tsx`,
  from `apps/web` with `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_PRODUCT_TELEMETRY`
  blank: **14 files, 153 tests passed**, exit 0, no warnings.
- After the last rig resume correction, the five affected rig files passed
  **124 tests**, including 34 limb tests; exit 0, no warnings. The complete
  frontend coverage run below is the final whole-suite authority.
- Independent mathematical review checked 81 combinations of joint limits across
  the 14 articulated variants against visible source alpha. Continuous local
  deformation remained orientation-preserving. The geometry oracle separately
  bounds reversed, near-collinear alpha-clipped slivers below one tenth of a
  drawing-buffer pixel squared; it does not claim exact topology at arbitrary scale.
- Native browser captures cover eight identities, both variants, five contexts,
  resting observation and spontaneous scenes, light/dark, compact/large and a
  380-pixel viewport. Current capture scripts exited 0 with no browser errors.
  Every identity and variant was visually inspected; no detached joint, frozen
  fringe, obvious contour hole, shifted face/collar or distorted ring was observed.
- Hermetic native-app Playwright: **18 tests passed**, exit 0, 4.9 minutes,
  Chromium 156.0.8078.4 on Windows / RTX 4090 ANGLE D3D11. The suite checks
  every companion variant, shader/pixel agreement, containment, reduced motion,
  recovery and frozen history. Its 192 GPU samples retained at least 11 drawing-buffer
  pixels of edge clearance. Command from `apps/web/e2e`, with
  `E2E_MANAGED_SERVER=0` and `E2E_BASE_URL=http://127.0.0.1:3017`:
  `node node_modules/@playwright/test/cli.js test --config=playwright.config.ts smoke/avatar-limbs.spec.ts --project=chromium --reporter=list --output=../../../output/playwright/avatar-limbs-regression`.
  Warnings were the color-environment conflict, intentionally absent Firebase
  configuration and the fixtures' intentional voice 403. No unexpected browser
  console message was observed. The owned server and temporary app copy were removed.
- Coordinated `task test:frontend:coverage`: **1,457 files / 17,968 tests passed**,
  exit 0, no exclusions, 1,201.49 seconds. Statements 88.51%, branches 83.33%,
  functions 86.57%, lines 89.95%; all published global/scoped thresholds passed.
  Three jsdom notices concerned unsupported focus/navigation before the summary;
  no diagnostic followed it. This is not a warning-free claim.
- Complete `task lint:frontend` passed after the separately owned workbench
  complexity correction, including cold TypeScript and unchanged ratchets.
  Backend/static cross-cutting gates passed in the coordinated run. Strict-index
  documentation checks still report unindexed files; workspace documentation
  preview, mirror, findings register and budget passed. No index mutation or
  audit bypass was used. Concurrent Tools edits mean these runs certify what
  they loaded, not an entirely frozen repository or subsequent artistic work.
- The local evidence directory is `output/playwright/avatar-limbs/`: `qualification.md`,
  `verified/`, `rest-verified/`, `geometry-budget.json`, `frame-sample.json` and
  `bip-live.mp4`. It is generated evidence, not a runtime dependency.

### Qualification limits

The source remains frontal reviewed art on a shallow volume, without independent
fingers or hidden anatomy suitable for unrestricted turns. Static geometry/skin
data grows to keep the fine alpha detail attached; it is prepared once and never
uploaded anew per frame. The measured desktop GPU is NVIDIA RTX 4090 under Chrome;
the short frame sample is not a performance claim for physical Android/iOS devices.
Firefox and WebKit were not exercised. No Git mutation or deployment was performed.

## Owner-requested artistic refinement

After the limb browser suite passed, the owner explicitly extended this work to
precise scarf fitting and substantially more convincing animation and scenes,
using feature-film character animation as a quality reference. The following
work is authorized without another approval gate. The evidence above qualifies
the limb milestone; subsequent changes require fresh affected checks.

### Findings and direction

- Before this refinement, the scarf derived both image dimensions from collar width. Its
  declared height is unused, so band thickness and hanging length cannot be fitted
  independently. Live and fallback sway also disagree. Use one garment mapping
  for both surfaces and calibrate each anatomy from rendered evidence.
- Scene limbs followed one scalar body-stretch signal. Author readable
  poses for each action, with preparation, action, hold and recovery; hands and
  feet must support the action instead of merely echoing squash.
- Sparse sprung height targets make flights ease into a hover. Add continuous
  authored trajectories on the same clock, retain velocity on interruption, and
  establish contact during compression and landing.
- Mechanical, soft and humanoid bodies need distinct deformation and settling.
  Resting and speaking gestures should have coherent intent, quiet intervals and
  delayed extremities, preserving existing entropy and attention priorities.

### Execution and acceptance

- [x] Capture and inspect cold scarves on all selectable styles and variants,
      including live/fallback, turns, compact/large and both themes.
- [x] Fit garment coverage and attachment through a shared declaration and test
      anatomical landmarks, stable fallback and bounded painted contours.
- [x] Reauthor body performances and limb acting, with observable flight,
      support, asymmetric action and delayed recovery tests.
- [x] Inspect complete scene sequences at actual sizes across identities,
      calibrate defects, and preserve reduced-motion, interruption and containment.
- [x] Run affected suites and repository gates on the final artistic snapshot;
      record measured successes, warnings and concurrent-work limitations.
- [x] Remove the retired Smiley identity and its dedicated resources; verify
      persisted-preference fallback, shared-face behavior and catalogue surfaces.

### Implementation and review notes

The first scarf iteration uses measured texture landmarks and independent width,
band height and tail drop. Its shared mapping feeds the live mesh and CSS
fallback. Root review covered every style/variant in `after-second`; the owner's
subsequent correction below supersedes its fit verdict for BIP, Oscar and Nimbo.
Their revised closed collars stay attached to the body while only the knot/end
sways. Actual cloth pixels, turns, fallback and sampled buffer uploads are part
of final qualification.

The stage support writer uses measured source-alpha sole locations. Its pure
compensation precedes existing viewport projection and releases during flight;
floating identities acquire no floor. Shadow translation separates actual
travel from torso compensation. Independent review checked transform order,
variant invalidation, lifecycle and viewport priority. Focused support/writer
verification passed 55 tests across five files; targeted ESLint passed. This
establishes stage support, not independent foot inverse kinematics.

Review also caught two defects during scene refinement: a clipped flight curve
could hold its apex in a small viewport, and interruption of a small lean could
erroneously request a whole revolution. The behavioral oracles reproduce the
actual spring trajectory rather than accepting the authored keys alone. Final
scene and complete repository results are recorded after the source stabilizes.

### Owner correction — 2026-11-08

The owner rejected the first scarf refinement for BIP, Oscar and Nimbo. The
front-patch proportions passed technical checks but did not convey a scarf
wrapping around the character: BIP stopped short of the head base, Oscar sat
above the shoulder line, and Nimbo covered only the central lobe. Those captures
are retained as diagnostic evidence, not accepted final fit. Reconstruct the
lateral returns and anatomical attachment, then inspect both variants in front,
turns, motion and fallback before closing garment acceptance.

The owner also requested removal of Smiley. Remove its offered identity and
dedicated renderer/assets, preserve genuinely shared facial anatomy, and prove
that a previously persisted Smiley preference resolves to the current default
without resetting other widget preferences. Decorative mood emoji are unrelated.

The completed acting key-pose matrix contains a historical Smiley row. Retained
identities are qualified separately from that retired row; the source alpha
matte correction and revised scarves require their own final material captures.

### Further owner fit correction — 2026-11-08

Actual-size owner screenshots reject Oscar's straight, narrow scarf across the
suit and Nimbo's insufficient fabric height. The proven compositor must remain
unchanged while these two families receive new anatomical calibration. Oscar
needs a readable drape from the shoulder/neck line, with a convincing knot and
free end; Nimbo needs a visibly broader fabric band around the complete cloud.
Inspect both variants at the owner's display scale, in light and dark themes,
before closing fit acceptance. BIP is not part of this correction.

The implementation review accepted Oscar's second neckline revision and Nimbo's
broader band. Fresh verification passed all frontend unit tests and the complete
frontend static gate; final browser review covered both variants of the three
wrapped families on Chromium, Firefox and WebKit. Real-clock Oscar and Nimbo
scenes were recaptured with the final fits. The retained catalogue and the earlier
coverage/application runs retain their documented snapshot boundaries.

Qualification is not an assertion that every diagnostic is green: the strict
Chromium restoration comparison retains a one-pixel difference, and strict
documentation checks still reject paths missing from the Git index while the
workspace preview passes. Concurrent dashboard work is preserved. Exact commands,
counts, source fingerprints, artifacts and limitations are recorded in
`output/playwright/avatar-artistry/qualification.md`. No Git mutation or deployment
was performed.

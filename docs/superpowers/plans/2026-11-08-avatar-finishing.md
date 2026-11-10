# Avatar Finishing Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for scoped implementation and independent review. User authorization is already explicit; no further design approval is required.

**Goal:** Make every retained avatar visibly better directed while removing empty decorative motion, without rebuilding the renderer.

**Architecture:** Refine the existing native tapes, identity profiles and material port. Keep one clock, all source art and fitted scarf geometry; changes compose through the current rig and renderer seams.

**Tech Stack:** Existing TypeScript/React, native WebGL/CSS fallback, Vitest and Playwright.

**Spec:** [Approved finishing direction](../specs/2026-11-08-avatar-finishing.md).

## Global Constraints

- No Git operation, commit, deployment, dependencies, new public route or unrelated edit.
- Preserve all artwork, accepted scarf fits, one clock, lifecycle, reduced motion and static portraits.
- No weaker assertions or baselines. Before/after video evidence uses native timing and declares its limits.
- Concurrent cards/Tools/navigation work remains untouched; root owns global gates.

## Review Focus

- A retired scene must disappear from scheduling and explicit entry points, including fixture readers.
- A face must keep breathing and meaningful attention after decorative motion is removed.
- Speech/attention interrupting a held scene must preserve continuity and settle at rest.
- Small sizes and all variants must retain readable poses, ground contact and scarf attachment.
- Graphics failure, alpha edges and neutral material colour must remain correct.

## Tasks

### 1. Immutable baseline and native comparison harness

Owner: browser agent. Files: `apps/web/e2e/capture/`, existing
`apps/web/e2e/fixtures/avatar-limbs/`, evidence under
`output/playwright/avatar-finishing-20261108/`.

- [x] Secure an immutable copy and hashes before production changes; then release the edit freeze.
- [x] Record all retained families with both variants, idle, conversation and a purposeful scene.
- [x] Reuse those seeds/scenarios for after videos; record real clock/RAF, errors and frame intervals.

### 2. Directed scene vocabulary and character acting

Owner: rig implementer. Files: `rig/body-sketches.ts`, `body-scene.ts`,
`sketches.ts`, `acting-profile.ts`, `acting-scenes.ts`, `limb-rest.ts`,
`limb-speech.ts` and their tests.

- [x] Pin retirement of `body-roll`, `body-somersault`, `body-jig`, `dizzy` and
      `brow-groove`; remove their implementations and update actual consumers.
- [x] Keep purposeful scenes, select coherent preferences per identity and refine
      pose/phase timing with bounded limb asymmetry and recovery.
- [x] Test reachability, distinct character trajectories, no full rotations,
      finite channels, ground contact and interruption without jumps.
- [x] Run affected rig suites and hand source-based change evidence to an independent reviewer.

### 3. Quiet presence and removal of decorative flourishes

Owner: root. Files: `expression-engine.ts`, `rig/gestures.ts`, `rig/poses.ts`
and directly affected tests. Interfaces: existing `IdleGesture`, `resolveLoops`
and `gestureTapes`; keep contextual head orientation and breath couplings.

- [x] Inventory autonomous tilt/bounce/rock producers, distinguishing purposeful
      acknowledgment and breathing from periodic decoration.
- [x] Remove retired idle gestures from their vocabulary, weighting and dispatch;
      preserve gaze, blink, facial intention and native breathing.
- [x] Test all mood families, real output travel and unchanged transition continuity.

### 4. Bounded material and secondary-cloth refinement

Owner: renderer implementer after Task 2 handoff. Files: `volume/mesh-gpu.ts`,
its direct callers, cloth helpers/writers and their tests; coordinate any new
rig output with root before editing shared files.

- [x] Differentiate existing material families with neutral-preserving lighting;
      retain alpha/fringe/casing and allocation/disposal contracts.
- [x] Refine only the scarf free end using the existing clock and a shared GPU/CSS
      motion declaration; keep the band and geometry immutable.
- [x] Compare materials and worn movement in real browser captures; retain only
      visible improvements and verify fallback/context loss.

### 5. Whole-change qualification and documentation

Owner: root plus independent reviewer and browser agent.

- [x] Review every paired before/after video and both variants; inspect continuity,
      purposeful acting, reduced-motion/static behavior and compact display.
- [x] Run fresh affected tests, `task lint:frontend`, full frontend coverage,
      relevant browser journeys, and documentation gates without Git mutation.
- [x] Update `NATIVE_AVATAR_VOLUME.md`, `SPIRIT_AVATAR.md` and ADR-294 where the
      retirement changes their stated behavior; preserve historical evidence scope.
- [x] Record exact commands, counts, source hashes, limits and clean up only owned processes.

The owner forbids Git operations, so review packages use immutable file copies
and hashes instead of commits/worktrees. The implementation ledger is
`output/playwright/avatar-finishing-20261108/progress.md`.

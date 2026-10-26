# LIA world playable prototype implementation plan

> **For agentic workers:** Use superpowers:executing-plans, strictly inline. The owner explicitly authorized implementation, isolated worktree creation and empirical validation; no subagent, merge, commit or publication.

**Goal:** Deliver a playable, attractive MalinosLand-inspired isometric LIA scene with BIP, keyboard/mouse/touch movement, camera/zoom/minimap and honest desktop/mobile performance evidence.

**Architecture:** A typed authored world and pure projection/navigation/simulation model, an owned original Canvas 2D sprite renderer, and a localized React HUD in LIA's authenticated shell. This local single-player slice has no LLM, business mutation, private-data projection, multiplayer or inferred presence. Those are future authority adapters, not fake active features.

**Tech stack:** Existing Next/React/TypeScript, Canvas 2D, vitest, hermetic Playwright. No new package or lockfile changes.

**Spec:** [Accepted V1](../specs/2026-10-09-lia-isometric-world-v1-scope.md), [reference adoption](../specs/2026-10-20-lia-world-malinosland-reference.md), [global contracts](../specs/2026-10-09-lia-isometric-world-global-review.md).

## Global constraints

- Work only in C:/Users/jgouv/LIA-worktrees/lia-world-prototype; main and the other audit worktree remain untouched.
- Dependency junctions point to main; never install into or delete them. Isolated Docker runtime uses a copied source snapshot and read-only dependency volume.
- No real account/provider side effect in validation. No claim that desktop device emulation is a physical phone.
- Preserve LIA UI tokens, six languages, accessible controls, native browser zoom, account-owned teardown and existing audio/recording providers.
- Scope is the graphical foundation: clearly label local/prototype behavior, no inactive business stations presented as working integrations.
- Meaningful behavioral TDD; preserve all existing ratchets and add a measured scoped floor when justified.

## Review focus

1. Pointer cancel, blur, modal, visibility, keyboard focus and account switch must release movement/gestures.
2. Frame stalls, collision corners, invalid destinations and map bounds must not create teleportation or stuck inputs.
3. Minimap/free camera/zoom must never move the avatar; coordinate transforms must remain invertible.
4. Repeated mounting must not leak RAF callbacks, listeners, observers, texture canvases or private owner state.
5. Small viewports, translated text, software keyboard and reduced motion must leave recovery controls reachable.

## Task 1: deterministic world and movement

Files: src/features/world/{types,definition,geometry,navigation,simulation}.ts and __tests__/model.test.ts.
- [x] Write red tests for projection, camera anchoring/bounds, reachable places, collision, invalid paths, frame-rate consistency and bounded BIP autonomy.
- [x] Implement typed world metadata and shared deterministic model; no renderer imports.
- [x] Run tests, then cold adversarial review of malformed input, geometry and bounded work.

## Task 2: original isometric art and owned runtime

Files: src/features/world/{art,renderer,runtime,input,performance}.ts and behavior tests.
- [x] Test timing statistics, input ownership/cancellation and lifecycle before implementing.
- [x] Build original warm, detailed sprite kit and spacious landscape; cache static assets, cull viewport, bound DPR and release owned resources.
- [x] Implement frame-independent motion, click-to-walk, drag/pinch/wheel, follow/free/recenter and autonomous BIP.
- [x] Review teardown, long-frame recovery, render bounds and resource budgets; preserve honest measured frame/CPU metrics.

## Task 3: LIA integration and localized HUD

Files: src/features/world/{WorldPrototype,WorldHud,WorldMinimap,WorldDirections}.tsx, styles; dashboard/world/page.tsx; destination registry and icon; six locale dictionaries.
- [x] Test exposed commands/labels/focus and guarded account lifetime.
- [x] Add a client-lazy localized route, upper-right minimap, touch controls, BIP call, quality/help/metrics and accurate local-mode disclosure.
- [x] Keep renderer outside React frame state; use low-frequency snapshots, accessible controls and the existing shell/authentication.
- [x] Review navigation parity, responsive geometry and no accidental API/model calls.

## Task 4: runtime acceptance and maintenance handoff

Files: e2e/smoke/world.spec.ts, documentation/FAQ and scoped ratchets.
- [x] Run deterministic tests, static gates, i18n and relevant existing navigation/shell tests.
- [x] Run owned Docker runtime and hermetic real-browser journeys at desktop/mobile widths, reduced motion, engine variants and bounded CPU throttling.
- [x] Inspect actual screenshots, exercise walking/zoom/minimap/BIP, measure warm frames and repeated entry/exit. Correct observed failures before finalizing.
- [x] Add measured scoped coverage ratchet without weakening global floors; document actual passes, degraded/untested physical-device limits, usage and future extension seams.
- [x] Perform inline whole-change adversarial review and record its findings/fixes and all verification outcomes.

## Execution rulings

- Canvas 2D is selected for the bounded slice: avoids dependency changes to shared junctions, independent original art avoids importing another application's licensing/commercial stack, and the model remains separate from the renderer. Cost if wrong: replace one renderer after measured art/device evidence, without rewriting geometry, controls, authored data or LIA authority.
- A manual git worktree is used because the owner explicitly requires external placement and avoids EnterWorktree. Native attachment refused the unmanaged checkout; the ordinary worktree remains valid and is retained.
- Plan handoff/commits/subagent review are overridden by the owner's explicit inline autonomous implementation instruction. Review is performed here; no commit is created.

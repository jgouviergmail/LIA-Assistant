# Persistent landing video and beat-driven effects — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (native, inline). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** one `<video>` element that keeps playing across the public pages, docked when its frame is not on screen, stopped on the sign-in and dashboard routes; the beat on every page; six beat-driven effects.

**Architecture:** the root `[lng]` layout mounts `LandingVideoHost` (context + player); the landing section becomes a SLOT that registers its frame; the player is placed over the slot in document coordinates or docked bottom-left; the beat driver writes on `:root`; the effects are stylesheet rules reading `--beat`, `--beat-bar`, `--beat-hue`.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-01-persistent-landing-video-design.md`

## Global Constraints

- Transform/opacity only for anything that moves on the beat; nothing under `prefers-reduced-motion`.
- No raw `fetch` outside the allowlisted hook; no `setState` inside an effect (react-hooks ratchet); no ref returned by a hook and read at render (React Compiler rule).
- Six locales for every new label; Prettier from the host; `task lint:frontend` and the touched vitest areas green; e2e `landing-video.spec.ts` updated and run.
- Pages stay prebuilt and host-neutral: nothing of the media origin in the build.

## Review Focus

1. A slot that unmounts while the music plays: the element must keep playing (no remount, no `load()`), the dock must appear.
2. A stop route reached from the dock: paused and unmounted, nothing left in the DOM, no listener leak.
3. A muted video with no slot: hidden and paused, no dock, resumes when a slot comes back in view.
4. A resize or a late font: the framed player follows the slot (document coordinates re-measured).
5. A language switch: the host remounts and resumes from the session record within its age bound; an old record is ignored.

---

### Task 1: The driver writes three properties on `:root`

**Files:** Modify `apps/web/src/lib/landing/beat-sync.ts`; Test `apps/web/src/lib/landing/__tests__/beat-sync.test.ts`.

- [ ] Tests: `barIntensityAt` follows the bar beats only (a weak beat between two bars contributes nothing); `hueAt` is 0 on a bar, ±8 at the quarter cycles, continuous within a bar; the driver writes `--beat`, `--beat-bar`, `--beat-hue` on the host and removes all three on stop.
- [ ] Run → RED. Implement `barIntensityAt`, `hueAt` (`BEAT_HUE_DEGREES = 8`, `BEAT_HUE_CYCLE_BARS = 4`), the three writes with their epsilons. Run → GREEN.

### Task 2: Pure helpers — routes, placement, session record

**Files:** Create `apps/web/src/lib/landing/player-routes.ts`, `frame-placement.ts`, `player-session.ts` and their tests.

- [ ] `playerRouteKind('/fr/blog/x') === 'public'`, `'/fr/login' === 'stop'`, `'/fr/dashboard/chat' === 'stop'`, `'/fr' === 'public'`, an unknown first segment `=== 'stop'`; a completeness test reads `src/app/[lng]` and demands every top-level route (and every `(auth)` page) be declared.
- [ ] `placementFor({ top, left, width, height }, scrollX, scrollY)` adds the offsets and rounds to the pixel.
- [ ] `readResume()` / `writeResume()` on a storage double: ignores a malformed or too-old record, survives a throwing storage.

### Task 3: The slot and the host

**Files:** Create `landing-video-context.tsx`, `LandingVideoHost.tsx`, `LandingVideoPlayer.tsx`, `LandingVideoDock.tsx`; rewrite `LandingVideo.tsx` (slot + caption), `LandingVideoSection.tsx` (slot labels), `use-video-playback.ts` (slot element, no-slot = out of view), `use-beat-sync.ts` (host `:root`), `use-landing-video.ts` (`useIntersects` on an element); delete `LandingVideoPill.tsx`; mount in `app/[lng]/layout.tsx`; locales `landing.video.close`, `landing.video.dock_label` ×6.

- [ ] Rewrite `LandingVideo.test.tsx` around `<LandingVideoHost labels>{slot}</LandingVideoHost>`: every former behaviour, plus: the slot unmounting with the sound on keeps the element playing and docks; muted with no slot hides and pauses; a stop route unmounts; a slot back in view re-frames; close pauses and hides; the session record is written on unmount and read on mount.
- [ ] Run → RED. Implement. Run → GREEN. `page.test.tsx` and any layout test adapted.

### Task 4: The stylesheet — `:root[data-beat]`, the frame and the dock, the six effects

**Files:** Modify `globals.css`; add the hook classes in `LandingHeader.tsx` (`landing-logo`), `ChapterRail.tsx` (`cosmos-chapter-rail`), `InteractiveChatMockup.tsx` (`cosmos-demo-step-dot`).

- [ ] Retarget the beat rules; add C/D/E/G/H/J; the reduced-motion block covers them all; the frame (`.landing-video-frame`) and dock (`.landing-video-dock`) styles.

### Task 5: e2e and docs

- [ ] `landing-video.spec.ts`: controls by page-level test ids, `html[data-beat]`, dock instead of pill; a navigation journey (sound on → header link to the blog → still playing, the blog's `h2` transformed → « Se connecter » → no video element).
- [ ] ADR-330 amendment, `LANDING_PAGE.md` §10, CLAUDE.md pointer clause, memory.
- [ ] Gates: vitest areas, `task lint:frontend`, `task lint:i18n`, `task lint:docs:preview`, e2e against the dev server (the standalone build is the known trap).

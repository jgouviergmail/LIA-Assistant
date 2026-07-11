# Micro-interactions Batch — Implementation Plan

> Executed inline in the authoring session (same executor, full context). Work packages are
> ordered by dependency; each ends with its verification command. Spec:
> `docs/superpowers/specs/2026-07-11-micro-interactions-batch-design.md` (items I1–I11).
> No git actions by the implementer — the user commits.

## Global verification (after every WP)

- Targeted: `cd apps/web && pnpm vitest run <touched test files>`
- Final: full suite + `task lint:frontend` + i18n parity (pre-commit hook covers it; manual
  check: the 4 new keys exist in all 6 locales) + runtime UAT by the user (hot reload).

---

### WP1 — Reducer streaming phase (foundation for I2 + I11)

- Modify: `src/reducers/chat-reducer.ts` — `streaming.phase: 'progress' | 'answer'`
  (initial `'answer'`); `STREAM_START`/`STREAM_REPLACE` payloads accept optional
  `phase`; reducer stores it when provided, preserves it otherwise; reset on stream end
  follows existing sub-state clearing rules.
- Modify: `src/lib/sse-handlers/handlers.ts` — progress-message creators pass
  `phase: 'progress'`; `handleContentReplacement`/token path passes `phase: 'answer'`.
- Modify: `src/lib/sse-handlers/types.ts` if the action types live there.
- Test: extend `src/reducers/__tests__/chat-reducer` suite (new transitions) +
  `src/lib/sse-handlers/__tests__/handlers.progress.test.ts` expectations.

### WP2 — Active-stream threading + CSS for steps (I11) and caret (I2)

- Modify: chat page (`app/[lng]/dashboard/chat/page.tsx`) — pass `activeStreamId` and
  `streamPhase` (from reducer state) to `ChatMessageList`.
- Modify: `ChatMessageList.tsx` (2 new props → forward), `ChatMessage.tsx` (class
  `progress-steps` / `stream-caret` on the markdown wrapper of the active message only).
- Modify: `globals.css` — `.progress-steps` (dim old `em` lines, pulse + slide-in on the
  last one; selector pinned after DOM inspection) and `.stream-caret` (blinking `::after`
  caret on last block; `motion-reduce`: hidden).
- Test: ChatMessage-level class assertions are covered indirectly; reducer already tested
  in WP1; visuals → UAT.

### WP3 — Avatar hover-wake (I1) + mood-ring ping (I6)

- Modify: `components/psyche/AssistantAvatar.tsx` — local `hovered` state on the existing
  `group` wrapper (`animate={animateEmoji || hovered}`); `usePrevious`-style ref on
  `psycheState.mood_label`, one-shot `mood-ping` class (only when `animateEmoji`), removed
  `onAnimationEnd`.
- Modify: `globals.css` — `mood-ping` keyframe (scale + halo, motion-safe).
- Test: extend `AssistantAvatar.test.tsx` (hover mounts img on a history row; ping class
  appears on mood change and not on initial mount).

### WP4 — Relationship milestone toast (I7)

- Create: `components/psyche/PsycheMilestoneWatcher.tsx` (headless; hydration guard via
  previous `lastUpdated`; forward-only stage transitions; `toast.success`).
- Modify: chat page — mount the watcher. i18n: `psyche.milestone.{EXPLORATORY,AFFECTIVE,STABLE}` ×6.
- Test: `components/psyche/__tests__/PsycheMilestoneWatcher.test.tsx` (no toast on
  hydration, toast on forward transition, none on same/backward).

### WP5 — Living tab title (I5)

- Create: `src/hooks/useLiveTabTitle.ts` (interval alternation only while `active` and
  `document.hidden`; exact-restore on cleanup/visibility).
- Modify: chat page — `useLiveTabTitle(isStreaming)`. i18n: `chat.tab_title_writing` ×6.
- Test: `src/hooks/__tests__/useLiveTabTitle.test.ts` (fake timers: alternates when hidden,
  restores on deactivate/unmount).

### WP6 — Send takeoff (I3) + skill badge glimmer (I4)

- Modify: `components/chat/ChatInput.tsx` (one-shot class on submit, `onAnimationEnd`
  cleanup), `ChatMessage.tsx` (glimmer class on the ✦ badge), `globals.css`
  (`send-takeoff`, `badge-glimmer` keyframes). Visual-only → UAT.

### WP7 — Animated mood emoji in settings (I8)

- Modify: `components/psyche/PsycheStateSummary.tsx` — mood emoji through `AnimatedEmoji`,
  hover-gated. Visual-only → UAT.

### WP8 — Briefing stagger (I9)

- Modify: the briefing cards container (locate under `components/dashboard/`) — index-based
  `animate-fade-in-up delay-{100..600}` on mount. Visual-only → UAT.

### WP9 — Empty-chat greeting (I10)

- Modify: `scripts/assets/fetch_noto_animated_emoji.py` — `UI_EMOJIS = {"wave": "1f44b"}`
  best-effort group; run it. `ChatMessageList.tsx` empty state → `AnimatedEmoji` 👋 +
  `lia-float`. Asset presence verified by the run output.

### WP10 — Docs + full validation

- Docs: `PSYCHE_ENGINE.md` (I6/I7/I8 one-liners), `BRIEFING_DOMAIN.md` (I9).
- Full suite, `task lint:frontend`, i18n parity of the 4 new keys, `git status` hygiene,
  UAT handoff with the checklist of the 11 visuals.

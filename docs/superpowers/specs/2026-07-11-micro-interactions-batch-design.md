# Design Spec — Micro-interactions Batch (11 items)

- **Status:** Implemented and shipped in v1.23.10 (I9 closed as a no-op — see the amendment).
- **Date:** 2026-07-11
- **Feature flag:** none (cosmetic frontend-only; every item degrades to today's behavior)
- **Parent:** follows `2026-07-11-chat-typing-variants-animated-psyche-avatar-design.md` — same
  guardrails: zero new npm dependency, `prefers-reduced-motion` respected everywhere, at most
  one *permanent* animation loop added per screen region, reuse of `AnimatedEmoji`
  (`components/ui/animated-emoji.tsx`) and of the existing keyframe library
  (`globals.css`, `lia-components.css`).

> Language note: English, to match the rest of `docs/`.

---

## Items

### I1 — Hover-wake history avatars (chat)

`AssistantAvatar` gains local hover state: `animate={animateEmoji || hovered}` on its
`AnimatedEmoji`. Historical mood snapshots wake while hovered, sleep on leave — the
one-permanent-loop rule is preserved (hover loops are transient, one at a time).

### I2 — Streaming caret (chat, answer phase)

A blinking caret at the end of the assistant text **while tokens stream**. Requires the
phase distinction from I11 (`streaming.phase === 'answer'`): `ChatMessage` receives
`isActiveStream` + phase and adds a `stream-caret` class on the markdown wrapper; CSS
`::after` on the last block child renders the caret (steps phase gets step styling instead,
never both). Hidden under `motion-reduce` (a static caret is noise, not information).

### I3 — Send button takeoff (chat input)

One-shot animation on submit: the send icon translates up-right and fades, then snaps back
(`send-takeoff` keyframe, ~450 ms, class toggled on submit, removed `onAnimationEnd`).
Pure decoration — never delays or blocks the actual send.

### I4 — Skill badge glimmer (chat)

The `✦ {skillName}` badge in assistant bubbles gets a slow background glimmer (gradient
sweep keyframe, ~4 s cycle) — active-skill feels "charged". Static under `motion-reduce`.

### I5 — Living tab title (app-wide, the only *useful* one)

While a run is streaming **and the tab is hidden**, alternate `document.title` between the
original title and `✦ {t('chat.tab_title_writing')}` every ~1.5 s; restore the exact
original title on done/visible/unmount. New i18n key `chat.tab_title_writing` ×6 locales.
Implemented as a small hook (`useLiveTabTitle(active: boolean)`) called from the chat page.

### I6 — Mood-ring ping on mood change (psyche)

When the live avatar's `mood_label` changes between renders (previous value tracked with a
ref, only when `animateEmoji` — history snapshots never change), the ring plays a one-shot
`mood-ping` keyframe (scale + fading halo in the ring color, ~1.2 s, removed
`onAnimationEnd`). Initial mount never pings (ref starts at current value). `motion-safe`
only.

### I7 — Relationship milestone toast (psyche)

New headless watcher component (`components/psyche/PsycheMilestoneWatcher.tsx`) mounted on
the chat page: observes `usePsycheStore().relationshipStage`; on a **forward** transition
(ORIENTATION → EXPLORATORY → AFFECTIVE → STABLE order index increases) **after hydration**
(previous `lastUpdated` non-null — the initial store default must never toast), fires
`toast.success(t('psyche.milestone.<stage>'))` with a ✨ icon. 3 new i18n keys
(`psyche.milestone.EXPLORATORY|AFFECTIVE|STABLE`) ×6 locales. Stages are one-way and rare —
the store transition itself guarantees once-per-stage.

### I8 — Animated mood emoji in psyche settings

`PsycheStateSummary` renders its current-mood emoji through `AnimatedEmoji` with
hover-to-animate (same pattern as personality menu items). No permanent loop added to the
settings page.

### I9 — Briefing cards stagger-in (dashboard)

> **Implementation finding: already shipped.** `BriefingCard` already applies
> `motion-safe:animate-in fade-in slide-in-from-bottom-2 duration-500` with a
> per-card `animationDelay` driven by the `staggerIndex` prop (60 ms × index, capped
> at 8). No change was made — the item closes as a no-op.

### I10 — Empty-chat animated greeting

The empty chat state swaps the static `MessageSquare` icon for an `AnimatedEmoji` 👋
(`1f44b`, waving hand — present in the Noto animated set) with a gentle `lia-float`. The
fetch script gains a `UI_EMOJIS` best-effort group (same rules as personalities). Static
glyph fallback unchanged.

### I11 — Animated execution steps (pipeline progress)

Today the progress message accumulates markdown lines `*📋 execution.steps.…*` via
`STREAM_REPLACE`; every update re-renders the whole list, so naive entrance animations would
replay on all lines.

Design:
- **Reducer phase (typed, tested):** `streaming.phase: 'progress' | 'answer'` added to the
  chat reducer state; `STREAM_START`/`STREAM_REPLACE` payloads gain an optional
  `phase` field. Progress handlers (`handleRouterDecision`, `handleExecutionStep`) send
  `'progress'`; the token path (`handleContentReplacement` / normal append) sends
  `'answer'`. Reducer tests cover the new transitions (project rule: a reducer test for
  every new action shape).
- **Rendering:** the chat page passes `activeStreamId` + `streamPhase` to `ChatMessageList`
  → `ChatMessage` adds `progress-steps` (phase `progress`) or `stream-caret` (phase
  `answer`, I2) on the markdown wrapper of the active message only.
- **CSS (`progress-steps`):** step lines render as `<em>` elements — older steps dim to
  ~55 % opacity, the **last** step pulses gently (opacity breathing) and slides in
  (`step-in` animation on the last `em` only, so re-renders never re-animate old lines).
  The exact selector (`em:last-of-type` vs `p:last-child em`) is pinned at implementation
  after inspecting the rendered DOM shape (single `<p>` with `<br>` vs one `<p>` per line).
  Step emojis stay plain text (animating Noto inside the markdown pipeline is out of scope).
- Scoped styling: the classes apply only to the active streaming message, so italic text in
  finished answers is never affected.

---

## Cross-cutting

- **i18n:** 4 new keys total (I5 ×1, I7 ×3) — all 6 locales, no plural forms (zh parity
  trivially satisfied). Everything else is visual-only.
- **Testing:** reducer phase transitions (I11), `AssistantAvatar` hover-wake (I1),
  `PsycheMilestoneWatcher` logic incl. hydration guard (I7), `useLiveTabTitle` restore
  behavior (I5). Purely-visual items (I3, I4, I9, I10, CSS of I11) are validated in runtime
  UAT — asserting keyframe names in jsdom proves nothing.
- **Error handling:** every item is presentation-only; failures degrade to current behavior
  (missing 👋 asset → static glyph via `AnimatedEmoji`; toast i18n key missing → i18next
  fallback value; title hook always restores on cleanup).
- **Docs:** one-line additions where the surface is already documented
  (`PSYCHE_ENGINE.md` for I6/I7/I8, `BRIEFING_DOMAIN.md` for I9). No ADR (cosmetic).
- **Out of scope:** sounds, confetti, theme-transition animations (rejected during
  brainstorm); animating emojis inside markdown content; any backend change.

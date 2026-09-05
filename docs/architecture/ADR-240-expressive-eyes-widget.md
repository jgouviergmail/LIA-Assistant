# ADR-240 — Expressive eyes widget: a pure expression engine over existing signals

**Date**: 2026-08-20
**Status**: Accepted
**Context**: Make LIA more expressive and playful in the chat interface: a
small floating widget of two solid cartoon eyes — movable, resizable,
hideable — that reacts to the whole conversation lifecycle (user message,
thinking/search phase, answer streaming, response content) and lives an idle
loop shaped by the psyche mood, the time of day, notifications and
inactivity.

## Decision

### 1. All expressivity derives from signals that already exist — zero backend

The chat FSM (`chat-reducer` status + `streaming.phase`), the SSE
`execution_step` metadata (`step_type: 'reasoning'` vs tool steps), the HITL
card state, the voice-mode FSM, the notification callbacks and the psyche
stores already describe every moment the eyes need. The widget adds **no
endpoint, no migration, no setting**. Weather flavor was deliberately
dropped from v1: the only weather source (`GET /briefing/cards`) triggers
all nine section fetchers — an unacceptable side effect for a decorative
widget. A read-only Redis "peek" endpoint is the documented v2 path.

### 2. A pure decision-table engine, rendering split from behavior

`expression-engine.ts` is fully pure (injected RNG, injected clocks): a
priority chain `error > HITL > voice > interaction > post-response reaction >
notification > typing > inactivity > idle(mood × hour)` resolves one of 20
expressions. `ExpressiveEyes` is purely declarative (data-attribute +
CSS custom properties); ALL motion lives in `styles/eyes.css`. The visual
language is Cozmo-derived (owner panel selection 2026-08-20): wide glowing
screen-rectangles whose lids are PURE geometric morphs — vertical compression
with a variable anchor, per-eye rotation for slants, 4-radius border morphs
(dome = joy, slit = focus) — deliberately no clipping, so every intermediate
state stays a smooth shape; squash & stretch, per-emotion arrival dynamics,
a 40-120 ms left/right phase offset. The idle loop layers gaze wander,
weighted gestures, mini mood-flicker scenes and rare slapstick beats (swap /
bump / spin / jelly) over the baseline. `useEyesBehavior` owns every timer
(blinks, heartbeat, dozing-off, wink, gaze homing — wander returns are
unkillable by design, so the eyes always come exactly home) and pauses
everything while the tab is hidden or the widget minimized;
`prefers-reduced-motion` freezes the eyes into static poses.

### 3. Per-turn reaction: the psyche self-report first, a language-neutral heuristic as fallback

The response LLM already appraises its own exchange (`psyche_eval` tag →
`active_emotions` in the SSE done snapshot) — that IS the per-turn,
content-driven signal, at zero extra cost. Because the psyche update is
fire-and-forget (the done can win the race) and psyche can be disabled, a
fallback heuristic reads the final text using **only punctuation, emoji and
structure** (trailing `?`/`？`, `!`/`！` density, emoji classes, code
fences, generated artifacts) — no word matching, so all 6 locales behave
identically.

### 4. Preferences are client-side display state

Visibility, size preset (S/M/L) and position (viewport percentages, so a
saved spot survives resolution changes and is re-clamped at mount/resize)
persist in localStorage via a `zustand/persist` store. Deliberately outside
the SEC-035 purge registry: pure device display preference, no personal
data, no consent record. Hiding the widget leaves a restore dot (the
CompanionPresence doctrine: never fully gone) and shuts down the entire
live machinery.

### 5. Surfaces — the same widget on the public landing (amended 2026-09-05)

The widget is mounted on the landing too (`LandingEyes`, loaded with
`next/dynamic` and `ssr: false` so the rig is never on the first page's
critical path), because a visitor who has not signed in is the one person the
character should charm. Nothing structural was needed: the root was already
fixed to the viewport, the position already persisted as viewport
percentages and re-clamped on resize, and the widget needs no account — its
three chat signals sit at rest, the psyche store defaults to disabled (the
graceful degradation of §1), and everything the face does on its own since
ADR-264 (breath, gestures, mimics, sketches) plays on a resting expression.

One decision, the owner's: **a position is kept per surface**
(`EyesSurface`: `chat` | `landing`, `position` and `landingPosition` in the
store). The chat docks its widget between two header anchors and clamps it
off the Delete button; the landing has no dock and its default is a corner
(`bottom-6 right-6`). A spot dragged on the landing must not become the
chat's spot. Size and visibility stay shared — they are the character's
preferences, not the page's. The LOOK is the one exception: the landing
forces the capsules (`styleId` on the widget, an owner choice) because a
visitor has no preference yet and the page has a face to present, while the
chat keeps the user's own style untouched.

## Consequences

- The chat page passes three props (`chatStatus` — newly exposed by
  `useChat` —, `streamPhase`, `hitlAwaiting`); everything else flows through
  two new stores (`eyesSignalsStore` ephemeral, `eyesWidgetStore`
  persisted). `handleExecutionStep` gained one extracted signal-recording
  helper (kept under the CC ratchet).
- CompanionPresence (off-chat pages) and the eyes (chat page) are
  complementary; unifying them is an open v2 arbitration.
- 126 new tests pin the engine matrix, the stores, the widget chrome and
  the wiring; none waits on an animation (jsdom emits no `animationend`).

# Design Spec — Wow-Effects Batch (6 items, shipped in v1.23.12)

- **Status:** Implemented and shipped in v1.23.12 (v1.23.11 was released in between by a separate backend workstream, ADR-126).
- **Date:** 2026-07-11
- **Feature flag:** none — same guardrails as the two previous batches: pure frontend,
  zero new dependency, hard fallbacks, every animation registered against
  `prefers-reduced-motion` (explicit kill-switch list), psyche visuals behind the existing
  display gate. Plan is inlined (§ Execution order) — items are micro-sized.

> Recon findings folded in: `lia-rain-drop` / `lia-sun-rays` keyframes confirmed **dormant**
> (defined in `lia-components.css`, zero users); `WeatherData.condition_code` carries the
> OpenWeatherMap main code ('Clear', 'Rain', 'Snow', …); the landing `ChatMockup` is
> timeout-driven with static bubbles and its own reduced-motion static path.

---

## W1 — Landing ChatMockup at product level

The mockup's scenario 1 `planning` bubble becomes a live 3-line steps block mirroring the
real product: lines appear staggered (`step-in`), each line dims when the next lands
(pure-CSS chained delayed animations — no new JS timers), the last one breathes
(`step-breathe`). Scenario 3's `status` line gets the breathe treatment, and the Markdown
reply's intro line ends with a **transient blinking caret** (3 blinks then gone,
`caret-blink … 3 both`). Reuses the existing keyframes; adds the utility classes
`animate-step-in` / `animate-step-breathe` in `globals.css` (also usable elsewhere).
**i18n:** 2 new keys ×6 (`landing.chat_mockup.step_analyze`, `step_draft`) — the steps
shown before `lia_planning`. The mockup's reduced-motion static path renders all lines
undimmed (kill-switch classes registered).

## W2 — Mood glow on the active bubble

The assistant bubble of the message being streamed (`isActiveStream`, psyche state present)
takes a thin border + soft outer glow in the current mood color: class `mood-glow` +
CSS var `--mood-color` (from `getMoodColor(...).hex`, already resolved in `ChatMessage`).
Static color (not motion) → no reduced-motion concern; a `transition` smooths mood shifts.
Gate closed / stream done → today's border, byte-identical.

## W3 — Rare emotion particles

In `AssistantAvatar` (live avatar only): when the active emotion CHANGES to a whitelisted
one with intensity ≥ 0.8, a one-shot burst of 3 particles rises from the avatar
(absolute spans, staggered `particle-up` animations, `pointer-events-none`, removed on
last `animationEnd`). Whitelist (restraint is the point):
`joy ✨, wonder 🌟, tenderness ❤️, gratitude 💖, enthusiasm ⚡, pride 🌟, frustration 💢`.
Unlisted emotions or lower intensity → nothing. Same never-on-mount ref guard as the mood
ping. Skipped entirely under reduced motion.

## W4 — Animated emoji in the milestone toast

`PsycheMilestoneWatcher` toast icon becomes `<AnimatedEmoji glyph="✨" animate …/>`
(the `2728.webp` asset already ships). Static ✨ fallback via the component's own gates.

## W5 — Progress → answer cross-fade

The first real token currently replaces the steps abruptly. The active message's markdown
wrapper gets `key={isActiveStream ? streamPhase : 'static'}`: the one `progress → answer`
flip remounts it once, playing a 300 ms `phase-fade` entrance. Historical messages keep a
stable key (no remounts); within a phase the key is stable (no per-token remount).

## W6 — Living weather on the WeatherCard

The dormant keyframes come alive on the card's hero emoji, driven by
`condition_code`: **Rain/Drizzle/Thunderstorm** → 3 falling droplet glyphs
(`lia-rain-drop`, staggered); **Snow** → same fall, ❄, slower; **Clear** → a subtle
rotating rays halo behind the emoji (`lia-sun-rays`, slow, low opacity). Other codes →
nothing. Utility classes added next to the keyframes in `lia-components.css`, registered
in that file's own reduced-motion section. Purely decorative overlay (`aria-hidden`,
`pointer-events-none`); the emoji itself is untouched.

---

## Cross-cutting

- **i18n:** W1 only — 2 keys ×6 locales, no plurals.
- **Tests:** W3 (burst gating: whitelist, threshold, never-on-mount, change-only),
  W5 (key stability contract via ChatMessage render), W2 (style var presence when active +
  gate closed fallback). W1/W4/W6 are static-markup/visual — UAT (+ W4 is 3 lines on a
  tested component).
- **Version surfaces are already pre-bumped to v1.23.11 by the user** (package.json ×2,
  `changelogVersionKeys`); the FAQ changelog **entries** `v1_23_10`→`v1_23_11` for the 6
  locales must be written at release time — the wired key currently has no content.
- **Out of scope:** sound, per-token fade, View Transitions (rejected in brainstorm).

## Execution order

1. WW1 CSS utilities + shared keyframes additions (`step-in`/`breathe` utilities,
   `phase-fade`, `particle-up`, weather classes) + reduced-motion registrations.
2. WW2 W2 mood glow + W5 cross-fade (both in `ChatMessage`) + tests.
3. WW3 W3 particles in `AssistantAvatar` + tests.
4. WW4 W4 toast icon.
5. WW5 W6 WeatherCard wiring.
6. WW6 W1 ChatMockup + i18n ×6.
7. WW7 Full validation (vitest, prettier, lint) + UAT checklist.

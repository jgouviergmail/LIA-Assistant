# Design Spec — Chat Typing Indicator Variants & Animated Psyche Avatar

- **Status:** Implemented and shipped in v1.23.10, v1.1 — amended after runtime UAT (see Amendments).
- **Date:** 2026-07-11

> **Amendments after UAT (same day):**
> 1. **D-2 dropped** — the psyche tint/tempo on the typing indicator was reverted on user
>    feedback: the indicator keeps its original gray color and nominal speed; only the
>    random shape variants (D-1) shipped.
> 2. **§4.4 resize reverted** — the Pillow 128px re-encode flattened the variable per-frame
>    timings of the Google encode and made the animations visibly choppy. The 512px
>    originals are shipped unmodified (the spec's documented fallback); the fetch script
>    defaults to `--size 0` with the reason recorded in its docstring.
> 3. **Follow-up (same day): personality selector animated** — user request after delivery.
>    The img/fallback logic was extracted into the shared `AnimatedEmoji` component
>    (`components/ui/animated-emoji.tsx`), the asset directory was renamed
>    `psyche-emoji/` → `animated-emoji/`, and the header selector animates the current
>    personality permanently + menu items on hover/focus (codepoints derived at runtime
>    from the DB-managed emoji, best-effort — 10/14 seeded emojis have Noto animations).
- **Feature flag:** none (cosmetic, frontend-only; gated by the existing psyche display setting and `prefers-reduced-motion`)

> Language note: English, to match the rest of `docs/`. Code identifiers verbatim.

---

## 1. Context & Goal

Two chat-polish features, requested together:

1. **Typing indicator variety** — the current indicator (`TypingIndicator.tsx`) is three gray
   bouncing dots, identical on every response. Goal: a small set of tasteful, fun animation
   variants picked at random per response, tinted by the assistant's current psyche mood.
2. **Animated psyche avatar** — the mood avatar next to assistant messages
   (`AssistantAvatar.tsx`) already reflects the Psyche Engine (14 moods → static Unicode emoji +
   colored ring, `psyche-colors.ts`). Goal: replace the static glyph with an **animated emoji**
   (self-hosted Noto Animated Emoji) so the "live" LIA feels alive.

Both features are pure frontend polish: no backend change, no new settings, no new i18n keys,
no new npm dependency.

---

## 2. Locked Design Decisions

| #   | Decision | Rationale |
|-----|----------|-----------|
| D-1 | Typing indicator = **6 pure-CSS variants**, one picked at random per response, stable for the duration of that response. | User choice (option B). Zero dependency, fits existing keyframe conventions in `globals.css`. |
| D-2 | Variant **color** follows the current mood (`getMoodColor(...).hex` via `usePsycheStore`); **speed** is modulated by `mood_arousal` (bounded factor). | User choice (option B): psyche-tinted. |
| D-3 | Psyche visuals share one gate: tint applies iff `storeState.enabled && storeState.displayAvatar` (same condition `ChatMessage` already uses for the avatar fallback). Otherwise: current gray dots at nominal speed. | Consistency with existing gating; no mood leakage when the user hid psyche visuals. |
| D-4 | Avatar animation = **self-hosted Noto Animated Emoji WebP**, one per mood (14), rendered via plain `<img>`. | User choice (option A). Animated WebP plays natively in `<img>` — no player library. |
| D-5 | **Only the latest assistant message** renders the animated emoji; all older messages keep the static glyph. | Found in self-review: `AssistantAvatar` renders per message — N looping WebPs would burn CPU/battery and look noisy. Also semantically right: history rows are mood *snapshots*; only the live LIA is animated. |
| D-6 | Reduced motion: the typing indicator **swaps to the static three-dot layout** (never a frozen variant); the avatar **does not render (nor fetch) the WebP** — static glyph instead. | Found in self-review: a frozen `orbit`/`equalizer` looks broken; a `display:none` img still downloads. Uses the codebase's direct `matchMedia('(prefers-reduced-motion: reduce)')` pattern (e.g. `AnimatedCounter.tsx`). |
| D-7 | Assets live in `apps/web/public/psyche-emoji/` with a license/attribution file. | Self-hosting is chosen for privacy (no per-user requests to Google) and availability — note: `img-src` actually allows `https:` in `csp.ts` (needed for Google profile avatars), so this is a policy choice, not a CSP constraint (corrected post-UAT). |
| D-8 | **Lot 1 is a de-risk spike**: verify all 14 codepoints exist in the Noto animated set, pin the exact license (CC BY 4.0 vs Apache-2.0 depending on distribution channel), and validate the re-encode tooling — before any component work. | Coverage and license are asserted, not proven; animated-WebP resizing needs libwebp/ffmpeg tooling (Pillow is not sufficient). |
| D-9 | No ADR. Docs touched: `docs/technical/PSYCHE_ENGINE.md`, `docs/knowledge/22_psyche.md`. | Cosmetic feature, no architectural decision. |

---

## 3. Feature 1 — Typing indicator variants

**Files:** `apps/web/src/components/chat/TypingIndicator.tsx` (sole consumer:
`ChatMessageList.tsx:251`), keyframes appended to `apps/web/src/styles/globals.css` next to the
existing chat keyframes.

### 3.1 Variants

| id | Visual |
|----|--------|
| `wave` | The 3 dots, smooth traveling wave (refined version of today's bounce). |
| `orbit` | 3 dots orbiting the center. |
| `equalizer` | 4 thin vertical bars dancing at staggered phases. |
| `sparkle` | A `✦` glyph twinkling/rotating (echoes the existing skill badge `✦`). |
| `breathe` | A ring inflating/deflating (echoes the avatar mood ring). |
| `typewriter` | Dots typed one by one, then erased. |

### 3.2 Mechanics

- **Selection:** `useState(() => VARIANTS[Math.floor(Math.random() * VARIANTS.length)])`.
  The component mounts when `isTyping` flips to true (conditional render in `ChatMessageList`),
  so the pick is stable per response and re-rolled on the next response. Client-only,
  post-interaction render → no SSR/hydration concern.
- **Tint:** when the D-3 gate is open, the wrapper sets inline `color: <mood hex>`; shapes use
  `currentColor` / `bg-current`. Gate closed → existing gray classes.
- **Speed:** duration factor `clamp(1 − 0.3 × mood_arousal, 0.7, 1.3)` (arousal ∈ [−1, 1]),
  exposed as a CSS variable (e.g. `--lia-typing-factor`) consumed by the variant keyframe
  classes via `calc()`. Gate closed → factor 1.
- **Reduced motion:** variant wrapper is `motion-reduce:hidden`; a static three-dot fallback
  (`hidden motion-reduce:flex`) sits alongside. The existing global
  `prefers-reduced-motion` kill-switch in `globals.css` remains as belt-and-braces.
- **A11y:** `role="status"`, `aria-live`, `aria-label={t('chat.assistant_typing')}` unchanged.
  Variants are purely decorative — no new text, no new i18n keys.

---

## 4. Feature 2 — Animated psyche avatar

**Files:** `apps/web/src/lib/psyche-colors.ts` (add `codepoint` to `MoodColorConfig`),
`apps/web/src/components/psyche/AssistantAvatar.tsx` (rendering),
`apps/web/src/components/chat/ChatMessage.tsx` + `ChatMessageList.tsx` (latest-message prop).

### 4.1 Mood → codepoint mapping

| Mood | Glyph | Codepoint | Mood | Glyph | Codepoint |
|------|-------|-----------|------|-------|-----------|
| serene | 😌 | `1f60c` | content | 😊 | `1f60a` |
| curious | 🧐 | `1f9d0` | determined | 😤 | `1f624` |
| energized | 😁 | `1f601` | defiant | 😠 | `1f620` |
| playful | 😜 | `1f61c` | resigned | 😔 | `1f614` |
| reflective | 🤔 | `1f914` | overwhelmed | 😵 | `1f635` |
| agitated | 😟 | `1f61f` | tender | 🥰 | `1f970` |
| melancholic | 😞 | `1f61e` | neutral | 😐 | `1f610` |

The Unicode glyph stays in the config as the permanent fallback.

### 4.2 Rendering rules (`AssistantAvatar`)

New prop `animateEmoji?: boolean`. The animated `<img>` renders iff **all** of:

1. `animateEmoji` is true (parent says this is the latest assistant message);
2. psyche state is present (existing condition);
3. `prefers-reduced-motion` is NOT reduced (direct `matchMedia` check, codebase pattern);
4. no prior load error for this mood (component state; `onError` flips to the static glyph).

Otherwise: current static `<span>{icon}</span>`, byte-for-byte today's behavior.

- `<img src="/psyche-emoji/{codepoint}.webp" alt="" aria-hidden loading="lazy">`, sized to the
  current glyph box (~24 px inside the 40 px ring). Accessible naming stays where it is today
  (ring div + tooltip).
- The existing streaming `animate-pulse` stays on the ring, unchanged.

### 4.3 Latest-message computation

`ChatMessageList` computes the index of the last `role === 'assistant'` message once per render
and passes `isLatestAssistant` to `ChatMessage`, which forwards it as `animateEmoji`.
`ChatMessage` is `memo`ized — the boolean flips only for the outgoing and incoming latest
messages, so exactly two rows re-render on each new response.

During streaming the streaming bubble *is* the latest assistant message → animated while LIA
answers. Phones never fetch the assets: the avatar column is `hidden mobile:block` and
`mobile:` = min-width 880 px (`--breakpoint-mobile`, `globals.css`).

### 4.4 Asset pipeline (Lot 1 spike)

One-shot script `scripts/assets/fetch_noto_animated_emoji.py` (Python, matching the repo's
`scripts/` tooling; may shell out to `img2webp`/ffmpeg for the resize step):

1. Downloads the animated WebP for the 14 codepoints from the Noto Animated Emoji distribution.
2. **Fails loudly** on any missing codepoint (the mood then needs a substitute emoji — decided
   at spike time, not silently skipped).
3. Re-encodes to ~128 px (~20–30 KB each, ~400 KB total) **if** animated-WebP tooling
   (libwebp `img2webp` / ffmpeg) is workable on the host. Documented fallback: ship the 512 px
   originals as-is — acceptable because at most one animated img renders at a time (D-5),
   assets are browser-cached, and phones never fetch them (§4.3).
4. Writes `apps/web/public/psyche-emoji/LICENSE` with the exact license + attribution.
   **If the license cannot be pinned to CC BY 4.0 / Apache-2.0 (or equivalent), the feature
   stops at the spike** and we fall back to design option C (CSS animation on Unicode glyphs).

### 4.5 Scope boundary

Only the chat avatar animates. Other psyche surfaces (`PsycheStateSummary`, `PsycheHistory`,
settings, onboarding) keep static glyphs — possible later extension, out of scope here.

---

## 5. Error handling

- Missing/corrupt asset at runtime → `onError` → static glyph (single state flip, no retry loop).
- Unknown mood label → `getMoodColor` already falls back to `neutral` (unchanged).
- Psyche store absent/disabled → gray indicator at nominal speed; static avatar — today's exact
  behavior.

---

## 6. Testing (vitest, existing setup — `matchMedia` is already mocked in `__tests__/setup.ts`)

- **TypingIndicator:** renders exactly one variant; pick is stable across re-renders of the same
  mount; gray fallback + factor 1 when the D-3 gate is closed; tint + bounded factor when open;
  static three-dot fallback present with `motion-reduce` classes.
- **AssistantAvatar:** `img` src matches the mood codepoint; `onError` falls back to the glyph;
  static glyph when `animateEmoji` is false; no `img` under reduced motion.
- **ChatMessageList/ChatMessage:** only the last assistant message receives
  `isLatestAssistant`/`animateEmoji`.

---

## 7. Documentation

- `docs/technical/PSYCHE_ENGINE.md` — short "avatar animation" section (rendering rules, D-5).
- `docs/knowledge/22_psyche.md` — user-facing mention.
- CHANGELOG/FAQ at release time via the standard release process. No ADR (D-9).

---

## 8. Out of scope

- Animated emoji on non-chat psyche surfaces (§4.5).
- Textual quips in the typing indicator (would cost 6-language i18n for decoration).
- Lottie/GIF pipelines, any npm dependency.
- A dedicated settings toggle — the existing psyche display setting + OS reduced-motion are the
  controls.

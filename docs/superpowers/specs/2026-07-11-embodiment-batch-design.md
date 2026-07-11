# Design Spec — Embodiment Batch (behavioral micro-interactions)

- **Status:** Implemented and shipped in v1.23.13 (F2 journal deliberately deferred).
- **Date:** 2026-07-11
- **Guardrails:** same as prior batches — pure frontend (except F2), zero new dependency, hard fallbacks, `prefers-reduced-motion` covered (explicit kill-switch list), reuse existing keyframes/assets/`AnimatedEmoji`. INLINE implementation, no subagents (user instruction).

> **Principle carried from the mood-glow removal:** ship *meaning*, not ambient decoration. Every effect here reflects a real system behavior.

## Reconnaissance findings (verified, not assumed)

- **`psyche_dream_cycle` is WEEKLY** (Sunday 03:00 UTC, first-person narrative), NOT a nightly memory consolidation — my original pitch was partly wrong. The genuine nightly jobs are `memory_consolidation` (~05:00 UTC, `settings.memory_consolidation_hour`), `memory_cleanup`, and `interest_cleanup` (03:00 UTC). ⇒ the "LIA rests / tidies its memories at night" copy is grounded in **memory consolidation/cleanup**, stated without false precision (no claim that a specific job fires for this exact user right now).
- **Journal extraction is a deferred fire-and-forget task** (`safe_fire_and_forget(extract_journal_entry_background(...))` at the end of `response_node`), gated by 4 skip conditions (automated source / journals disabled / trivial turn / no user), and the LLM decides afterward whether to write. ⇒ at `done` time only "extraction *scheduled*" is known, never "entry *written*". This forces the F2 design fork (below).
- `lia-bell-ring` keyframe exists (`lia-components.css`). Proactive messages render through the normal assistant branch (`AssistantAvatar`), detected via `isInterestNotificationMetadata` / `metadata.type startsWith 'proactive_'`.
- `UpdatedAtBadge.showJustUpdated` ("mis à jour ✨", 1.5 s) **exists but is dormant** — never passed `true`. F5 = wire it, not invent.
- User timezone: the empty-chat state will use the browser's own local hours (`new Date().getHours()`) — simplest and equal to the user's wall-clock in practice; no tz lib.

---

## F1+F3 — Time-aware empty-chat state (merged)

The empty-chat hero emoji (currently always 👋) becomes time-of-day aware, in the user's local hours:

| Bucket (local) | Emoji | Codepoint | Copy |
|----------------|-------|-----------|------|
| 5–10 morning | ☕ | `2615` | existing title/description |
| 11–17 day | 👋 | `1f44b` | existing (unchanged) |
| 18–22 evening | 🌙 | `1f319` | existing |
| 23–4 deep night | 😴 | `1f634` | existing + a truthful sub-line |

- Deep-night adds one new i18n key `chat.empty_state.night_note` ×6 — grounded copy ("La nuit, LIA range ses souvenirs" / "At night, LIA tidies its memories") referencing the real nightly consolidation. No specific-job claim.
- Rendered via `AnimatedEmoji` (static-glyph fallback on missing asset / reduced motion). Assets ☕/🌙/😴 added to the fetch script's `UI_EMOJIS`, best-effort.
- Pure presentation; a bad clock or missing asset degrades to a plain glyph. No test needed beyond bucket-function unit coverage (`greetingForHour`).

## F4 — Embodied proactive notifications

When a proactive message (interest / heartbeat / `proactive_*`) **arrives live**, its avatar ring plays a one-shot `lia-bell-ring` and the mood/personality emoji animates on arrival.

- **Live-only guard (critical):** a proactive message loaded from history must NOT ring. Heuristic mirroring the milestone hydration guard: ring only when `Date.now() - message.timestamp < 10_000` at mount (a live push has a near-now timestamp; history rows are older). One-shot on mount, removed `onAnimationEnd`.
- New `AssistantAvatar` prop `ring?: boolean` → applies the bell-ring animation class on the ring wrapper (motion-safe, reduced-motion registered). `ChatMessage` computes the freshness heuristic and passes it.
- Test: `greetingForHour` buckets (F1) + the proactive-freshness predicate.

## F5 — Breathing freshness on briefing cards

Wire the dormant `showJustUpdated`: `BriefingCard` tracks the `isRefreshing` `true → false` transition (a completed refresh) and passes `showJustUpdated` to `UpdatedAtBadge` for ~1.6 s. Reuses the existing badge machinery entirely.

- Implemented with a `useEffect` + previous-value ref + timeout, cleaned up on unmount. No new i18n (badge key exists).
- Test: the transition predicate/hook if extracted; otherwise covered by UAT (BriefingCard full render needs heavy mocks — like the existing stagger, validated in UAT).

---

## F2 — Visible journal (PRESENTED, not built — product fork)

Reconnaissance forces a decision the user must make, because journal extraction is deferred and probabilistic:

- **Option A — deterministic intent (recommended, ~½ day, low risk).** Add a boolean to the `done` metadata set where the 4 guards already decide (`journal_reflecting`), true when extraction is *scheduled*. Frontend shows a transient "✍️ …" after `done`. Honest copy must say **"LIA réfléchit à cet échange"** (true by construction) rather than "a écrit dans son carnet" (not yet known). No new SSE *type* ⇒ the SSE symmetry test is untouched; only a metadata field. Trap to respect: `DoneMetadata` ≠ `STREAM_DONE` metadata (two types to keep in sync — noted in memory).
- **Option B — confirmed outcome (accurate, >1 day, more surface).** The extraction task persists its real result (wrote / skipped) to Redis keyed by thread; the frontend surfaces it on the next interaction. Accurate but loses the "just after this reply" immediacy and adds moving parts.

**Recommendation:** Option A with the "réfléchit" copy — magical yet truthful, minimal backend surface, no SSE-contract impact. Await the user's pick before touching the backend.

## Execution order

1. Assets (extend `UI_EMOJIS`, run fetch). 2. F1+F3 empty-chat + i18n ×6 + `greetingForHour` test. 3. F4 avatar `ring` + freshness guard + test. 4. F5 `BriefingCard` freshness wiring. 5. Full validation. 6. Present F2.

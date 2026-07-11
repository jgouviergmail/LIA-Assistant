# Design Spec — Companion Presence (floating mini-avatar)

- **Status:** Implemented and shipped in v1.23.13.
- **Date:** 2026-07-11
- **Guardrails:** pure frontend, zero new dependency, hard fallbacks, `prefers-reduced-motion` covered, INLINE (no subagents). **Lesson from the mood-glow removal: a persistent, always-visible element must carry meaning and stay unobtrusive — every state here reflects a real system signal, and the companion is dismissable.**

## Reconnaissance (verified)

- **Mount point:** `app/[lng]/dashboard/layout.tsx` wraps every dashboard page — the correct home for a persistent element.
- **Psyche is global** (`usePsycheStore`, zustand) → the "rest" appearance (mood emoji + ring) is available everywhere.
- **Notifications SSE is chat-page-only** today (`useNotifications` instantiated in `chat/page.tsx` only). On settings/faq/home there is **no** active subscription → the companion needs its own layout-level subscription to react to notifications off-chat.
- **Active-run signal exists:** `fetchActiveRun()` (`@/lib/api/chat`) → `GET /api/v1/agents/runs/active` returns `{ active, stream_id }` (ADR-117). This is the real "working" signal, pollable cheaply.
- **No double subscription:** the companion is **hidden on the chat page** (where the real `AssistantAvatar` already lives). When hidden it also **disables its SSE + polling**, so exactly one notifications connection is ever active (chat's OR the companion's, never both).

## States (a single avatar, base animation + overlay badge)

| Signal | Source | Rendering |
|--------|--------|-----------|
| **rest** (default) | — | mood `AnimatedEmoji` + mood ring, gentle `animate-greet-float` |
| **working** | `fetchActiveRun().active === true` (poll ~6 s, off-chat only) | a small "thinking" bubble above the avatar reusing `TypingIndicator`; ring gets a soft pulse |
| **notification** (overlay) | unread proactive/reminder/subagent/scheduled count from the layout SSE | count badge (top-right) + one-shot `animate-bell-ring` on arrival |

- Base animation is rest **or** working; the notification badge is an independent overlay (both can show at once).
- Psyche disabled / no data → the classic "LIA" mini-badge instead of the mood emoji (reuses `AssistantAvatar`'s own fallback).

## Interactions

- **Click the avatar** → `router.push('/dashboard/chat')` and reset the unread count (they'll see the messages there).
- **Minimize** (small control on hover) → collapses to a tiny dot in the corner; clicking the dot restores. Session-scoped state (a `useState`, resets on reload) — deliberately un-persisted so it never permanently hides a signal.
- **Reduced motion:** float/pulse/bell-ring all registered in the kill-switch; the badge (information) stays.

## Architecture

- **`CompanionPresence` component** mounted once in the dashboard layout, after `{children}`.
  - `usePathname()` → `onChat = /dashboard/chat`. When `onChat` (or `dismissed`): render `null` **and** pass `enableSSE:false` / skip polling.
  - Reuses `useNotifications({ isAuthenticated, enableSSE: !onChat, enableFCM:false, onNotification })` — counts `proactive_*` / `reminder` / `subagent_result` / `scheduled_action`; battle-tested reconnect logic, no FCM double-handling.
  - `useEffect` + `setInterval` (6 s, gated `!onChat && !dismissed && authenticated`) calling `fetchActiveRun()` → `working`. Cleared on unmount / route change.
  - Reads `usePsycheStore` for the mood emoji (via the existing `AssistantAvatar` or a small inline render).
- **Pure helpers (tested):**
  - `isChatRoute(pathname): boolean` — hide/disable gate.
  - `deriveCompanionState({ working, unreadCount }): { base: 'rest'|'working'; showBadge: boolean; badgeCount: number }` — the display contract.
- **i18n (×6):** `companion.open_chat`, `companion.minimize`, `companion.restore`, `companion.aria_state` (with `{count}` for notifications). ~4 keys.
- **CSS:** reuse `animate-greet-float`, `animate-bell-ring`, `TypingIndicator`; add one `companion-*` positioning class if needed. All animations already in the reduced-motion list.

## Testing

- Unit: `isChatRoute` (chat vs settings/faq/home/localized paths), `deriveCompanionState` (rest, working, badge thresholds, working+badge combo).
- Runtime (nip.io:3000 unlock): companion floats on settings/faq/home (rest), **hidden on chat**, click → navigates to chat, minimize/restore. Console clean, no hydration warning (client-only via a `mounted` gate like the empty-chat greeting). Working/notification live-triggering is best-effort (same limits as F4).

## Out of scope / deferred

- Persisting minimize across reloads (deliberately session-only).
- Drag-to-reposition, speech bubbles with proactive content preview (future).
- Mobile: shown on mobile too (fixed corner), but sized down; the chat-page hide still applies.

## Execution order

1. Pure helpers + tests. 2. `CompanionPresence` component (rest + click + minimize + mounted-gate). 3. Wire notifications SSE (badge) + active-run poll (working). 4. Mount in layout. 5. i18n ×6. 6. Validate (vitest/prettier/lint). 7. Runtime verify.

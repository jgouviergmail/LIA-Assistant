# Compact World Social Interface Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Check off the behavioral deliverables after verification.

**Goal:** Add proximity-selected compact messaging and directly accessible social gestures while preserving the full conversation panel.

**Architecture:** Keep one mailbox client, shared drafts and consent state for both presentations. Project nearby candidates from the authoritative World snapshots; proximity chooses the recipient and never changes server permissions. Compose mobile controls in reserved areas rather than overlapping absolute anchors.

**Tech Stack:** Existing React, TypeScript, CSS, Vitest and Playwright; no dependencies or backend changes.

**Spec:** User-approved design in this chat (2026-10-28): retain Discuter; nearest reachable peer within two tiles, otherwise public; visible recipient with manual choice; preserve the destination while composing; compact recent history and input; all six gestures at the bottom; add space below the date.

**Phone refinement:** The compact bar starts hidden on phone and short landscape layouts. Discuter opens it; the person may hide/show recent history, open the full conversation, or close the bar while retaining the draft. Desktop retains the initially visible compact bar.

## Global Constraints

- Preserve all pre-existing staged and unstaged work; do not commit or stage unrelated changes.
- Retain account/permission guards, explicit translation consent, uncertain-send recovery and private/public draft separation.
- Mobile gestures use six touch targets, a 3-by-2 grid where needed, with no menu required.
- Keep mobile keyboard, safe areas, landscape and desktop layouts usable.
- Use the six existing locales and existing UI primitives.

## Review Focus

- A moving peer must never redirect a draft or an in-flight send.
- A wall or unavailable snapshot must not select a nearby person incorrectly.
- Opening the full panel must preserve drafts without duplicating polling or sending.
- The compact surface must not pause world navigation merely by being visible.
- Gestures, joystick, contextual actions and keyboard must not overlap.

### Task 1: Authoritative nearby candidate projection

Files: `useWorldSession.ts`, a focused proximity helper and its tests; reuse navigable route geometry.

- [x] Write and run failing tests for exact two-tile reach, walls, nearest ordering and inactive sessions.
- [x] Expose a stable ordered `nearbyParticipants` projection without publishing every position into React state.
- [x] Verify the helper and session tests.

### Task 2: Direct gestures and heading spacing

Files: `WorldEmoteControls.tsx`, `WorldPrototype.tsx`, `WorldHud.tsx`, responsive CSS and gesture tests.

- [x] Test direct access to all six gestures, disabled state and one keyboard listener.
- [x] Add a bottom presentation sharing the existing gesture callbacks; keep the expanded menu.
- [x] Reserve bottom control geometry and add spacing below the sky/date line.
- [x] Verify gestures and responsive behavior.

### Task 3: Shared compact conversation

Files: `WorldMessageControls.tsx`, `WorldShared.tsx`, compact component/state helper/CSS, six locale files and messaging tests.

- [x] Test nearest/public selection, manual selection, focus/draft locking, departed recipients, shared drafts and send recovery.
- [x] Add the compact presentation using the existing mailbox owner, explicit consent and separate draft keys.
- [x] Preserve full Discuter, reduce/expand controls and recent scrolling history; hide the compact surface when another private panel owns attention.
- [x] Verify compact and existing messaging tests, including the phone open/reduce/close/reopen cycle.

### Task 4: Qualification and review

- [x] Exercise mobile portrait/landscape and desktop in a browser, with control collisions and a unit-tested keyboard viewport. The final three-engine matrix passes all 12 cases.
- [x] Run frontend tests and lint: final full coverage passes 15,026 tests; frontend lint, indexed documentation, documentation preview and i18n pass. The initial full lint's pre-existing Git-index documentation references are resolved by concurrent staging.
- [x] Review the scoped diff and update this plan with outcomes; leave changes uncommitted. Preserve concurrent staging and remove only the QA server's verified generated artifacts.

Final evidence is recorded in the [qualification](../qualification/2026-10-28-world-compact-social.md).

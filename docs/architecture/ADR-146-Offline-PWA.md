# ADR-146: Offline PWA — Unified Service Worker & Branded Offline Page (D5)

**Status**: ✅ IMPLEMENTED (2026-07-23)
**Date**: 2026-07-23
**Deciders**: jgouvier + Claude (security program, arbitration A7 decided 2026-07-23)
**Technical Story**: `docs/superpowers/specs/2026-07-23-security-account-program.md` (F18/F19) — only a push-only SW existed, registered at scope `/` and ONLY inside the FCM permission flow; an offline PWA showed the raw browser error.

## Decision

- **One unified SW (A7)** — `firebase-messaging-sw.js` KEEPS its historical URL (existing registrations update in place; two SWs cannot share scope `/`) and now owns push AND offline: precached `offline.html` + icons, network-first navigations with the branded offline fallback, stale-while-revalidate for same-origin static assets. **Never cached**: `/api/*`, non-GET, cross-origin, `text/event-stream` — personal data must not land on disk.
- **Unconditional registration** — `ServiceWorkerRegistration` component at the app layout (production only; a caching SW poisons `next dev`); the FCM flow reuses the same registration (idempotent).
- **Versioning as a guarded release surface** — `CACHE_VERSION` constant in the SW must equal `package.json` version, enforced by `src/__tests__/service-worker.test.ts` (same executable-guard pattern as the FAQ changelog key); `activate` deletes stale `lia-shell-v*` caches; `Cache-Control: no-cache` on the SW file in `next.config.ts` so new releases deploy promptly.
- **Offline page** — self-contained `public/offline.html` (inline CSS, light/dark via `prefers-color-scheme`, retry button) with **inline i18n ×6** selected from the i18next cookie / `navigator.language`; parity asserted by the SW test (the i18n pre-commit hook cannot see a static file).

## Consequences

- Reconnection needs no extra machinery: the ADR-117 reattach/resume path already covers chat recovery.
- Full browser-offline proof requires a production build (the SW is dev-disabled); the hermetic e2e suite keeps covering the app itself — documented as a CI-managed-server concern.
- Rejected: two SWs with split scopes (pure migration risk, zero functional gain — F18); build-time version injection into `public/` (rewrites a versioned file at each build; the guarded constant is simpler and test-enforced).

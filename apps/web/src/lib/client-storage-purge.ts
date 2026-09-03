/**
 * Central registry of browser-stored keys that must not survive a logout.
 *
 * SEC-035 — some client state is stored under a GLOBAL key rather than one
 * namespaced per account. On a shared browser profile (a family laptop, a
 * kiosk), signing out of A and into B leaves A's data readable by B: the
 * browser has no notion of "the previous user".
 *
 * Per-user keys (e.g. the chat draft, keyed by user id) do not belong here —
 * they are cleared by their own owner at logout. This registry is specifically
 * for the keys that CANNOT be attributed to a user once written.
 *
 * Add every new sensitive client-side key here rather than sprinkling
 * `removeItem` calls across components: a purge that lives in one place is the
 * only one that stays complete.
 */

import {
  DEBUG_METRICS_HISTORY_KEY,
  GEOLOCATION_CACHE_KEY,
  GEOLOCATION_ENABLED_KEY,
  GEOLOCATION_REACTIVATION_DISMISSED_KEY,
  LAST_LOCATION_PUSH_TS_KEY,
  MEETING_RECORDER_STATE_KEY,
} from '@/lib/constants';

/** Keys in `sessionStorage` cleared on logout. */
export const SENSITIVE_SESSION_STORAGE_KEYS: readonly string[] = [
  DEBUG_METRICS_HISTORY_KEY,
  // Banner-dismissal marker: account-linked decision under a global key —
  // account B must not inherit A's "don't offer reactivation this session".
  GEOLOCATION_REACTIVATION_DISMISSED_KEY,
];

/**
 * Keys in `localStorage` cleared on logout.
 *
 * SEC-034 — geolocation. The cache holds raw coordinates, and the enabled flag
 * is a consent record: leaving either behind means account B reads where
 * account A was, and keeps collecting position under A's decision. Both keys
 * are global, so neither can be attributed to its owner after the fact —
 * exactly the category this registry exists for.
 */
export const SENSITIVE_LOCAL_STORAGE_KEYS: readonly string[] = [
  GEOLOCATION_CACHE_KEY,
  GEOLOCATION_ENABLED_KEY,
  // Last-location push marker: account-linked, written under a global key —
  // left behind, account B's session would inherit A's throttle window and
  // skip its own first push (generalized last-known location, 2026-08-16).
  LAST_LOCATION_PUSH_TS_KEY,
  // Meeting recorder state (ADR-258): names an account's live meeting id —
  // account B must never be offered to resume or finalize A's recording.
  MEETING_RECORDER_STATE_KEY,
];

/**
 * Marker recording which account the sensitive storage above belongs to.
 *
 * Logging out is not the only way to change accounts: a session can simply
 * expire, and the next person signs in through the same tab without any logout
 * ever running. `sessionStorage` survives that, so the purge cannot hang on the
 * logout path alone — ownership has to be checked when an identity is
 * established too.
 */
const STORAGE_OWNER_KEY = 'lia.storageOwner';

/**
 * Remove every registered sensitive key from browser storage.
 *
 * Never throws: storage is unavailable in private mode and in SSR, and a
 * failing purge must not prevent the logout itself from completing.
 */
export function purgeSensitiveClientStorage(): void {
  if (typeof window === 'undefined') return;

  for (const key of SENSITIVE_SESSION_STORAGE_KEYS) {
    try {
      window.sessionStorage.removeItem(key);
    } catch {
      // Storage unavailable — nothing to purge.
    }
  }

  for (const key of SENSITIVE_LOCAL_STORAGE_KEYS) {
    try {
      window.localStorage.removeItem(key);
    } catch {
      // Storage unavailable — nothing to purge.
    }
  }

  try {
    window.sessionStorage.removeItem(STORAGE_OWNER_KEY);
  } catch {
    // Storage unavailable — nothing to purge.
  }
}

/**
 * Purge sensitive storage when it belongs to a different account.
 *
 * Called whenever an identity becomes known. A plain "purge on login" would
 * wipe the user's own data on every page reload — the point of this state is to
 * survive navigation — so the previous owner is recorded and compared instead.
 *
 * @param userId - Identifier of the account that owns the session now.
 */
export function purgeSensitiveClientStorageOnAccountChange(userId: string): void {
  if (typeof window === 'undefined' || !userId) return;

  let previousOwner: string | null = null;
  try {
    previousOwner = window.sessionStorage.getItem(STORAGE_OWNER_KEY);
  } catch {
    // Storage unavailable: nothing is persisted either, so nothing to purge.
    return;
  }

  if (previousOwner !== userId) {
    // Covers both "someone else was here" and "no owner recorded" — the latter
    // being data written before this marker existed, which cannot be attributed
    // and is therefore not ours to keep.
    purgeSensitiveClientStorage();
    try {
      window.sessionStorage.setItem(STORAGE_OWNER_KEY, userId);
    } catch {
      // Best effort: failing to stamp only means we purge again next time.
    }
  }
}

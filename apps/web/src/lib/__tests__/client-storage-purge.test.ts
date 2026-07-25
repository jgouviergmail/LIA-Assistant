/**
 * SEC-035 — sensitive client storage must not survive a logout.
 *
 * The debug metrics history is stored under a GLOBAL sessionStorage key and
 * contains the user's own request text plus execution details. On a shared
 * browser profile, account B could read what account A ran.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  DEBUG_METRICS_HISTORY_KEY,
  GEOLOCATION_CACHE_KEY,
  GEOLOCATION_ENABLED_KEY,
} from '@/lib/constants';
import {
  purgeSensitiveClientStorage,
  purgeSensitiveClientStorageOnAccountChange,
  SENSITIVE_LOCAL_STORAGE_KEYS,
  SENSITIVE_SESSION_STORAGE_KEYS,
} from '@/lib/client-storage-purge';

describe('purgeSensitiveClientStorage', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('removes the debug metrics history', () => {
    sessionStorage.setItem(
      DEBUG_METRICS_HISTORY_KEY,
      JSON.stringify([{ query: 'my private question' }])
    );

    purgeSensitiveClientStorage();

    expect(sessionStorage.getItem(DEBUG_METRICS_HISTORY_KEY)).toBeNull();
  });

  it('leaves unrelated keys untouched', () => {
    sessionStorage.setItem('lia.theme', 'dark');
    localStorage.setItem('lia.locale', 'fr');

    purgeSensitiveClientStorage();

    expect(sessionStorage.getItem('lia.theme')).toBe('dark');
    expect(localStorage.getItem('lia.locale')).toBe('fr');
  });

  it('is idempotent when nothing is stored', () => {
    expect(() => purgeSensitiveClientStorage()).not.toThrow();
    expect(sessionStorage.getItem(DEBUG_METRICS_HISTORY_KEY)).toBeNull();
  });

  it('does not throw when storage access is denied', () => {
    // Safari private mode and hardened profiles throw on access; a failing
    // purge must never block the logout it is part of.
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('QuotaExceededError');
    });

    expect(() => purgeSensitiveClientStorage()).not.toThrow();
  });

  it('registers the debug history key', () => {
    // Guards against the reducer and the purge registry drifting apart: the
    // reducer writes DEBUG_METRICS_HISTORY_KEY, the purge must clear that key.
    expect(SENSITIVE_SESSION_STORAGE_KEYS).toContain(DEBUG_METRICS_HISTORY_KEY);
  });

  it('removes the cached GPS coordinates (SEC-034)', () => {
    // The most directly personal thing the browser holds for this app, under a
    // global key: nothing ties it to the account that produced it.
    localStorage.setItem(
      GEOLOCATION_CACHE_KEY,
      JSON.stringify({ latitude: 48.8584, longitude: 2.2945, timestamp: 1 })
    );

    purgeSensitiveClientStorage();

    expect(localStorage.getItem(GEOLOCATION_CACHE_KEY)).toBeNull();
  });

  it('removes the geolocation consent flag (SEC-034)', () => {
    // Confidentiality is the lesser reason. This flag is a CONSENT record —
    // left behind, account B inherits account A's decision and the browser
    // starts collecting B's position without B ever agreeing to it.
    localStorage.setItem(GEOLOCATION_ENABLED_KEY, 'true');

    purgeSensitiveClientStorage();

    expect(localStorage.getItem(GEOLOCATION_ENABLED_KEY)).toBeNull();
  });

  it('registers both geolocation keys', () => {
    // The hook writes these two keys; the registry must clear the same two.
    expect(SENSITIVE_LOCAL_STORAGE_KEYS).toContain(GEOLOCATION_CACHE_KEY);
    expect(SENSITIVE_LOCAL_STORAGE_KEYS).toContain(GEOLOCATION_ENABLED_KEY);
  });
});

describe('purgeSensitiveClientStorageOnAccountChange', () => {
  const HISTORY = JSON.stringify([{ query: 'account A private question' }]);

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it('wipes the history when a different account signs in', () => {
    // The scenario a logout-only purge misses entirely: A's session expires,
    // B signs in through the same tab, no logout ever ran.
    purgeSensitiveClientStorageOnAccountChange('user-a');
    sessionStorage.setItem(DEBUG_METRICS_HISTORY_KEY, HISTORY);

    purgeSensitiveClientStorageOnAccountChange('user-b');

    expect(sessionStorage.getItem(DEBUG_METRICS_HISTORY_KEY)).toBeNull();
  });

  it('keeps the history across reloads for the same account', () => {
    // The feature exists to survive navigation — purging unconditionally on
    // sign-in would destroy the thing it protects.
    purgeSensitiveClientStorageOnAccountChange('user-a');
    sessionStorage.setItem(DEBUG_METRICS_HISTORY_KEY, HISTORY);

    purgeSensitiveClientStorageOnAccountChange('user-a');

    expect(sessionStorage.getItem(DEBUG_METRICS_HISTORY_KEY)).toBe(HISTORY);
  });

  it('does not let account B inherit account A position or consent (SEC-034)', () => {
    // The scenario that motivates SEC-034: a shared laptop. Without this, B's
    // assistant answers "the weather here" using A's coordinates, and keeps
    // collecting B's position under a consent B never gave.
    purgeSensitiveClientStorageOnAccountChange('user-a');
    localStorage.setItem(
      GEOLOCATION_CACHE_KEY,
      JSON.stringify({ latitude: 48.8584, longitude: 2.2945, timestamp: 1 })
    );
    localStorage.setItem(GEOLOCATION_ENABLED_KEY, 'true');

    purgeSensitiveClientStorageOnAccountChange('user-b');

    expect(localStorage.getItem(GEOLOCATION_CACHE_KEY)).toBeNull();
    expect(localStorage.getItem(GEOLOCATION_ENABLED_KEY)).toBeNull();
  });

  it('keeps the same account own position across reloads', () => {
    // Counterpart: the cache exists so a reload does not re-prompt for the
    // permission and re-query the GPS. Purging it every mount would be a
    // regression dressed as a fix.
    purgeSensitiveClientStorageOnAccountChange('user-a');
    localStorage.setItem(GEOLOCATION_ENABLED_KEY, 'true');

    purgeSensitiveClientStorageOnAccountChange('user-a');

    expect(localStorage.getItem(GEOLOCATION_ENABLED_KEY)).toBe('true');
  });

  it('wipes unattributable data left by an older build', () => {
    // No owner marker: the data predates this mechanism, so it cannot be
    // proven to belong to the current account.
    sessionStorage.setItem(DEBUG_METRICS_HISTORY_KEY, HISTORY);

    purgeSensitiveClientStorageOnAccountChange('user-a');

    expect(sessionStorage.getItem(DEBUG_METRICS_HISTORY_KEY)).toBeNull();
  });

  it('clears the owner marker on logout so the next account starts clean', () => {
    purgeSensitiveClientStorageOnAccountChange('user-a');

    purgeSensitiveClientStorage();
    sessionStorage.setItem(DEBUG_METRICS_HISTORY_KEY, HISTORY);
    purgeSensitiveClientStorageOnAccountChange('user-a');

    expect(sessionStorage.getItem(DEBUG_METRICS_HISTORY_KEY)).toBeNull();
  });

  it('ignores an empty user id', () => {
    sessionStorage.setItem(DEBUG_METRICS_HISTORY_KEY, HISTORY);

    purgeSensitiveClientStorageOnAccountChange('');

    expect(sessionStorage.getItem(DEBUG_METRICS_HISTORY_KEY)).toBe(HISTORY);
  });
});

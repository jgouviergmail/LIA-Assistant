/**
 * Unified service worker + offline page guards (D5, ADR-146).
 *
 * - CACHE_VERSION must track package.json (release-surface guard: a release
 *   that forgets the bump ships stale caches forever).
 * - The offline page must carry all 6 locales (it renders without the app
 *   bundle, so the i18n parity hook cannot see it).
 * - The SW must never cache API traffic (personal data on disk).
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';

import pkg from '../../package.json';

const swSource = readFileSync(
  join(process.cwd(), 'public', 'firebase-messaging-sw.js'),
  'utf-8'
);
const offlineSource = readFileSync(join(process.cwd(), 'public', 'offline.html'), 'utf-8');

describe('unified service worker', () => {
  it('pins CACHE_VERSION to the package version (release-surface guard)', () => {
    const match = swSource.match(/const CACHE_VERSION = '([^']+)'/);
    expect(match, 'CACHE_VERSION constant missing from the SW').not.toBeNull();
    expect(match![1]).toBe(pkg.version);
  });

  it('keeps the push handlers (offline shell must not evict FCM)', () => {
    expect(swSource).toContain("addEventListener('push'");
    expect(swSource).toContain("addEventListener('notificationclick'");
  });

  it('owns the offline lifecycle (install/activate/fetch + fallback)', () => {
    expect(swSource).toContain("addEventListener('install'");
    expect(swSource).toContain("addEventListener('activate'");
    expect(swSource).toContain("addEventListener('fetch'");
    expect(swSource).toContain('/offline.html');
  });

  it('never caches API traffic, non-GET, or event streams', () => {
    expect(swSource).toContain("url.pathname.startsWith('/api/')");
    expect(swSource).toContain("request.method !== 'GET'");
    expect(swSource).toContain('text/event-stream');
  });
});

describe('offline page', () => {
  it('carries all 6 locales inline (parity with the app languages)', () => {
    for (const lng of ['en', 'fr', 'de', 'es', 'it', 'zh']) {
      expect(offlineSource, `offline.html missing locale ${lng}`).toMatch(
        new RegExp(`${lng}: \\{`)
      );
    }
  });

  it('offers a retry action', () => {
    expect(offlineSource).toContain('location.reload()');
  });
});

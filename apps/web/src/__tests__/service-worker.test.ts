/**
 * Unified service worker + offline page guards (D5, ADR-146).
 *
 * - CACHE_VERSION must track package.json (release-surface guard: a release
 *   that forgets the bump ships stale caches forever).
 * - The offline page must carry all 6 locales (it renders without the app
 *   bundle, so the i18n parity hook cannot see it).
 * - The SW must never cache API traffic (personal data on disk).
 */

import { existsSync, readFileSync } from 'node:fs';
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

  // Regression 2026-07-24: the notification icon pointed at
  // '/icon-192x192.png' and the badge at '/badge-72x72.png' — neither file
  // exists. Nothing failed loudly: Next.js answers those paths with the HTML
  // app shell, the browser cannot decode it as an image and quietly falls
  // back, so every push shipped unbranded. The same class of typo in
  // PRECACHE_ASSETS is worse — cache.addAll() rejects and the SW never
  // installs at all.
  it('references only assets that exist in public/', () => {
    // Scan CODE, not prose: comments legitimately quote paths (including the
    // broken ones, to say why they are gone) and must not fail the guard.
    const swCode = swSource
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n')
      .filter(line => !line.trim().startsWith('//'))
      .join('\n');
    const referenced = [
      ...swCode.matchAll(/'(\/[A-Za-z0-9._/-]+\.(?:png|svg|ico|webp|html|json))'/g),
    ].map(match => match[1]);

    expect(referenced.length, 'no asset literal found — has the SW changed shape?').toBeGreaterThan(
      0
    );
    for (const asset of new Set(referenced)) {
      expect(
        existsSync(join(process.cwd(), 'public', asset)),
        `${asset} is referenced by the service worker but missing from public/`
      ).toBe(true);
    }
  });

  it('declares each lifecycle handler exactly once', () => {
    // Two install/activate pairs coexisted after the push SW and the offline
    // shell were merged (ADR-146); duplicated lifecycle handlers make
    // activation order a coin toss to reason about.
    for (const event of ['install', 'activate', 'fetch']) {
      const occurrences = swSource.match(new RegExp(`addEventListener\\('${event}'`, 'g')) ?? [];
      expect(occurrences, `${event} declared ${occurrences.length} times`).toHaveLength(1);
    }
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

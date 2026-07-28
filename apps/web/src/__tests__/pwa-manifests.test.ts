/**
 * PWA manifests + layout metadata (UXR Lot 9, A6).
 *
 * - The 6 localized manifests share ONE structure (a drift in any locale —
 *   missing shortcut, wrong start_url, absent maskable icon — fails here);
 * - generateMetadata preserves the historical SEO fields (the static-export →
 *   per-locale conversion must never cost OpenGraph/Twitter/title), localizes
 *   the manifest link, and uses a real PNG apple touch icon (iOS ignores SVG).
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

import { buildAppMetadata } from '@/lib/app-metadata';
import { validateLanguage } from '@/i18n';
import type { Language } from '@/i18n/settings';

const LANGS = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;

function manifest(lng: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(process.cwd(), 'public', `manifest-${lng}.json`), 'utf-8'));
}

describe('localized PWA manifests', () => {
  it.each(LANGS)('manifest-%s has the full installability structure', lng => {
    const m = manifest(lng);
    expect(m.lang).toBe(lng);
    expect(m.start_url).toBe(`/${lng}/dashboard`);
    expect(m.scope).toBe('/');
    expect(m.display).toBe('standalone');

    const icons = m.icons as { purpose: string; sizes: string; src: string }[];
    // 192+512 in BOTH purposes, as SEPARATE entries (a combined
    // "any maskable" gets cropped by launchers — recorded decision).
    for (const purpose of ['any', 'maskable']) {
      for (const size of ['192x192', '512x512']) {
        expect(icons.some(i => i.purpose === purpose && i.sizes === size)).toBe(true);
      }
    }
    expect(icons.every(i => i.src.endsWith('.png'))).toBe(true);

    const shortcuts = m.shortcuts as { url: string; name: string }[];
    expect(shortcuts).toHaveLength(3);
    expect(shortcuts[0].url).toBe(`/${lng}/dashboard/chat`);
    expect(shortcuts.every(s => s.name.length > 0)).toBe(true);

    expect(m.screenshots as unknown[]).toHaveLength(2);
    const share = m.share_target as { action: string; method: string };
    expect(share.action).toBe(`/${lng}/share`);
    expect(share.method).toBe('GET');
  });

  it('every manifest shares the exact same key set (structural parity)', () => {
    const keySets = LANGS.map(lng => Object.keys(manifest(lng)).sort().join(','));
    expect(new Set(keySets).size).toBe(1);
  });
});

describe('generateMetadata — SEO preservation guard', () => {
  it.each(['fr', 'en'])('keeps the historical fields and localizes the manifest (%s)', lng => {
    const meta = buildAppMetadata(lng as Language);
    expect(meta.title).toBe('LIA - Votre assistant personnel');
    expect(meta.manifest).toBe(`/manifest-${lng}.json`);
    expect(meta.openGraph?.siteName).toBe('LIA');
    expect(meta.twitter).toMatchObject({ card: 'summary_large_image' });
    const apple = (meta.icons as { apple: { url: string; type: string }[] }).apple[0];
    expect(apple.url).toBe('/apple-touch-icon.png');
    expect(apple.type).toBe('image/png');
  });

  it('falls back to a valid language for unknown locales (layout wrapper path)', () => {
    const meta = buildAppMetadata(validateLanguage('xx'));
    expect(String(meta.manifest)).toMatch(/^\/manifest-(en|fr)\.json$/);
  });
});

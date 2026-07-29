/**
 * PWA manifest parity guard (N-13).
 *
 * Six localized manifests, one per URL locale. Key parity alone would not
 * catch what actually broke: the "Document spaces" shortcut pointed at
 * `/dashboard/settings` for a year after the spaces page shipped, because
 * nothing compared the six files to each other or to the app's routes.
 *
 * What must hold, for every locale:
 *  - same number of shortcuts, same order of DESTINATIONS (path compared
 *    after stripping the locale prefix — names and query VALUES are localized
 *    on purpose, query KEYS are not);
 *  - every URL is locale-prefixed and starts inside the app scope;
 *  - localized query values survive decodeURIComponent (a mis-encoded draft
 *    would 404 nothing but silently prefill garbage).
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const LOCALES = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;

interface ManifestShortcut {
  name: string;
  url: string;
  icons?: { src: string; sizes: string }[];
}

interface Manifest {
  lang: string;
  start_url: string;
  shortcuts?: ManifestShortcut[];
}

function loadManifest(locale: string): Manifest {
  const raw = readFileSync(join(process.cwd(), 'public', `manifest-${locale}.json`), 'utf-8');
  return JSON.parse(raw) as Manifest;
}

/** `/fr/dashboard/chat?voice=1` → `{ path: '/dashboard/chat', keys: ['voice'] }`. */
function delocalized(url: string, locale: string): { path: string; queryKeys: string[] } {
  const parsed = new URL(url, 'https://placeholder.local');
  const prefix = `/${locale}`;
  expect(parsed.pathname.startsWith(prefix)).toBe(true);
  return {
    path: parsed.pathname.slice(prefix.length),
    queryKeys: [...parsed.searchParams.keys()].sort(),
  };
}

describe('PWA manifests — cross-locale parity', () => {
  const manifests = LOCALES.map(locale => ({ locale, manifest: loadManifest(locale) }));
  const reference = manifests[0];

  it('declares its own locale in lang and start_url', () => {
    for (const { locale, manifest } of manifests) {
      expect(manifest.lang).toBe(locale);
      expect(manifest.start_url).toBe(`/${locale}/dashboard`);
    }
  });

  it('offers the same number of shortcuts everywhere', () => {
    for (const { locale, manifest } of manifests) {
      expect(manifest.shortcuts?.length, `manifest-${locale}`).toBe(
        reference.manifest.shortcuts?.length
      );
    }
  });

  it('points every locale at the same destinations, locale prefix aside', () => {
    const referenceTargets = (reference.manifest.shortcuts ?? []).map(s =>
      delocalized(s.url, reference.locale)
    );
    for (const { locale, manifest } of manifests) {
      const targets = (manifest.shortcuts ?? []).map(s => delocalized(s.url, locale));
      expect(targets, `manifest-${locale}`).toEqual(referenceTargets);
    }
  });

  it('keeps every localized query value decodable', () => {
    for (const { locale, manifest } of manifests) {
      for (const shortcut of manifest.shortcuts ?? []) {
        const query = shortcut.url.split('?')[1];
        if (!query) continue;
        expect(
          () => decodeURIComponent(query),
          `manifest-${locale} ${shortcut.name}`
        ).not.toThrow();
      }
    }
  });

  it('gives every shortcut an icon (Android drops icon-less shortcuts)', () => {
    for (const { locale, manifest } of manifests) {
      for (const shortcut of manifest.shortcuts ?? []) {
        expect(shortcut.icons?.length, `manifest-${locale} ${shortcut.name}`).toBeGreaterThan(0);
      }
    }
  });
});

/**
 * Unit tests for the shared low-level utilities: Tailwind class merging,
 * Google-image proxy rewriting (COEP compatibility), UUID generation (secure
 * and insecure-context fallback), and accent-insensitive search normalization.
 */
import { describe, expect, it, vi } from 'vitest';

import {
  cn,
  findNormalizedMatches,
  generateUUID,
  normalizeSearchText,
  proxyGoogleImageUrl,
} from '../utils';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

describe('cn', () => {
  it('joins truthy classes and drops falsy ones', () => {
    expect(cn('a', false && 'b', undefined, 'c')).toBe('a c');
  });

  it('resolves conflicting Tailwind utilities (last wins)', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4');
    expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500');
  });
});

describe('proxyGoogleImageUrl', () => {
  it('rewrites Google user-content hosts through the auth proxy', () => {
    const url = 'https://lh3.googleusercontent.com/a/photo=s96';
    expect(proxyGoogleImageUrl(url)).toBe(
      `/api/v1/auth/profile-image-proxy?url=${encodeURIComponent(url)}`
    );
  });

  it('leaves non-Google URLs untouched', () => {
    expect(proxyGoogleImageUrl('https://example.com/pic.png')).toBe('https://example.com/pic.png');
  });

  it('returns null for a null/undefined input', () => {
    expect(proxyGoogleImageUrl(null)).toBeNull();
    expect(proxyGoogleImageUrl(undefined)).toBeNull();
  });

  it('returns an unparseable URL unchanged (catch branch)', () => {
    expect(proxyGoogleImageUrl('not a url')).toBe('not a url');
  });
});

describe('generateUUID', () => {
  it('uses crypto.randomUUID in a secure context', () => {
    const spy = vi
      .spyOn(crypto, 'randomUUID')
      .mockReturnValue('11111111-1111-4111-8111-111111111111');
    expect(generateUUID()).toBe('11111111-1111-4111-8111-111111111111');
    spy.mockRestore();
  });

  it('falls back to getRandomValues when randomUUID is unavailable', () => {
    const cryptoObj = crypto as unknown as { randomUUID?: () => string };
    const saved = cryptoObj.randomUUID;
    cryptoObj.randomUUID = undefined;
    try {
      const id = generateUUID();
      expect(id).toMatch(UUID_RE);
    } finally {
      cryptoObj.randomUUID = saved;
    }
  });
});

describe('normalizeSearchText', () => {
  it('lowercases and strips diacritics', () => {
    expect(normalizeSearchText('Café')).toBe('cafe');
    expect(normalizeSearchText('Gérard')).toBe('gerard');
    expect(normalizeSearchText('Ñoño')).toBe('nono');
    expect(normalizeSearchText('DÉJÀ')).toBe('deja');
  });

  it('folds the curly apostrophe onto the one a keyboard produces', () => {
    // Measured defect: "application d’authentification" (U+2019) could not be
    // found by typing "d'authentification", which is what every keyboard emits.
    expect(normalizeSearchText('d’authentification')).toBe("d'authentification");
    expect(normalizeSearchText('L‘Assistant')).toBe("l'assistant");
    expect(normalizeSearchText('lʼapp')).toBe("l'app");
    // Both directions: a query typed with the curly form must reach ASCII text.
    expect(normalizeSearchText("aujourd'hui")).toBe(normalizeSearchText('aujourd’hui'));
  });

  it('folds no-break spaces onto a plain space', () => {
    // French typography puts U+00A0 / U+202F before double punctuation; a
    // multi-word query is typed with plain spaces.
    expect(normalizeSearchText('Voix : activée')).toBe('voix : activee');
    expect(normalizeSearchText('50 %')).toBe('50 %');
  });

  it('never changes the character count', () => {
    // Load-bearing invariant, not a style preference: `findNormalizedMatches`
    // maps normalized offsets back to original ones by summing
    // `normalizeSearchText(char).length`. A folding that expanded (ß → ss) or
    // dropped a character would silently shift every highlight built on it.
    const samples = [
      'd’authentification',
      'Voix : activée',
      '50 %',
      'Café ‘quoted’ text',
      'Größe / cœur / æther',
      '简体中文の設定',
    ];
    for (const sample of samples) {
      // Diacritics are the one deliberate exception: a combining mark is
      // REMOVED, so only precomposed input keeps its length. Compare against
      // the accent-stripped baseline rather than the raw sample.
      const baseline = sample.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
      expect(normalizeSearchText(sample), `folding resized ${JSON.stringify(sample)}`).toHaveLength(
        baseline.length
      );
    }
  });

  it('keeps findNormalizedMatches aligned on folded text', () => {
    // The end-to-end proof of the invariant above: a query typed with the ASCII
    // apostrophe must select the ORIGINAL curly characters, at the right offsets.
    const text = 'Passkeys, application d’authentification et mot de passe.';
    const ranges = findNormalizedMatches(text, normalizeSearchText("d'authentification"));
    expect(ranges).toHaveLength(1);
    expect(text.slice(ranges[0].start, ranges[0].end)).toBe('d’authentification');
  });
});

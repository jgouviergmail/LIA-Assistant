/**
 * Unit tests for the shared low-level utilities: Tailwind class merging,
 * Google-image proxy rewriting (COEP compatibility), UUID generation (secure
 * and insecure-context fallback), and accent-insensitive search normalization.
 */
import { describe, expect, it, vi } from 'vitest';

import { cn, generateUUID, normalizeSearchText, proxyGoogleImageUrl } from '../utils';

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
});

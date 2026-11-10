import { afterEach, describe, expect, it, vi } from 'vitest';

import { cookieName, getLocaleCookie, languages, setLocaleCookie } from '../settings';

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = `${cookieName}=; path=/; max-age=0`;
  document.cookie = `other_${cookieName}=; path=/; max-age=0`;
});

describe('browser locale preference', () => {
  it.each(languages)('round-trips %s through the actual cookie store', locale => {
    setLocaleCookie(locale);
    expect(getLocaleCookie()).toBe(locale);
  });

  it('does not infer a preference from a missing cookie or another cookie name', () => {
    expect(getLocaleCookie()).toBeNull();
    document.cookie = `other_${cookieName}=en; path=/`;
    expect(getLocaleCookie()).toBeNull();
    setLocaleCookie('fr');
    expect(getLocaleCookie()).toBe('fr');
  });

  it.each(['', 'pt', 'zh-CN', 'FR', 'en=de'])('rejects an unsupported stored value %j', value => {
    document.cookie = `${cookieName}=${value}; path=/`;
    expect(getLocaleCookie()).toBeNull();
  });

  it('has no browser preference during server rendering', () => {
    vi.stubGlobal('document', undefined);
    expect(getLocaleCookie()).toBeNull();
    expect(() => setLocaleCookie('en')).not.toThrow();
  });
});

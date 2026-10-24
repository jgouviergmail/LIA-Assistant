/**
 * Cloudflare Turnstile on the password doors (ADR-364): the script is loaded once
 * per page and only when the instance publishes a site key; a failed load can be
 * retried; the refusal codes the API answers map to their own sentence.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  TURNSTILE_SCRIPT_URL,
  TURNSTILE_TOKEN_HEADER,
  loadTurnstile,
  resetTurnstileLoaderForTests,
  turnstileErrorKey,
  turnstileHeaders,
  turnstileLanguage,
  type TurnstileApi,
} from '../turnstile';

function fakeApi(): TurnstileApi {
  return { render: vi.fn(() => 'widget-1'), reset: vi.fn(), remove: vi.fn() };
}

function loaderScripts(): HTMLScriptElement[] {
  return Array.from(document.querySelectorAll<HTMLScriptElement>('script')).filter(
    s => s.src === TURNSTILE_SCRIPT_URL
  );
}

beforeEach(() => {
  resetTurnstileLoaderForTests();
  delete window.turnstile;
  for (const script of loaderScripts()) script.remove();
});

afterEach(() => {
  delete window.turnstile;
});

describe('loadTurnstile', () => {
  it('injects the explicit-render loader once, however many widgets ask', async () => {
    const first = loadTurnstile();
    const second = loadTurnstile();

    expect(loaderScripts()).toHaveLength(1);
    window.turnstile = fakeApi();
    loaderScripts()[0].dispatchEvent(new Event('load'));

    await expect(first).resolves.toBe(window.turnstile);
    await expect(second).resolves.toBe(window.turnstile);
  });

  it('answers at once when the script is already there', async () => {
    window.turnstile = fakeApi();

    await expect(loadTurnstile()).resolves.toBe(window.turnstile);
    expect(loaderScripts()).toHaveLength(0);
  });

  it('lets a failed load be tried again', async () => {
    const failed = loadTurnstile();
    loaderScripts()[0].dispatchEvent(new Event('error'));
    await expect(failed).rejects.toThrow();
    expect(loaderScripts()).toHaveLength(0);

    const retried = loadTurnstile();
    expect(loaderScripts()).toHaveLength(1);
    window.turnstile = fakeApi();
    loaderScripts()[0].dispatchEvent(new Event('load'));
    await expect(retried).resolves.toBe(window.turnstile);
  });

  it('refuses a script that loaded without defining the API', async () => {
    const loading = loadTurnstile();
    loaderScripts()[0].dispatchEvent(new Event('load'));

    await expect(loading).rejects.toThrow();
  });
});

describe('turnstileLanguage', () => {
  it.each([
    ['fr', 'fr'],
    ['de', 'de'],
    ['zh', 'zh-CN'],
    ['en', 'en'],
  ])('asks Cloudflare for %s as %s', (lng, expected) => {
    expect(turnstileLanguage(lng)).toBe(expected);
  });
});

describe('turnstileErrorKey', () => {
  it('names a refused check and an unavailable one, and nothing else', () => {
    const refusal = (error: string) => ({ data: { detail: { error } } });

    expect(turnstileErrorKey(refusal('turnstile_failed'))).toBe('auth.errors.turnstile_failed');
    expect(turnstileErrorKey(refusal('turnstile_unavailable'))).toBe(
      'auth.errors.turnstile_unavailable'
    );
    expect(turnstileErrorKey(refusal('demo_signup_limit_reached'))).toBeNull();
    expect(turnstileErrorKey(new Error('network'))).toBeNull();
    expect(turnstileErrorKey(undefined)).toBeNull();
  });

  it('names a refused sign-in sent without the widget a check blocked in this browser', () => {
    // The API refuses a tokenless sign-in only while Cloudflare answers IT: the
    // widget failed in this browser, where retrying cannot help and allowing
    // the challenge host can (ADR-364).
    const refusal = (error: string) => ({ data: { detail: { error } } });

    expect(turnstileErrorKey(refusal('turnstile_failed'), true)).toBe('auth.turnstile.blocked');
    expect(turnstileErrorKey(refusal('turnstile_unavailable'), true)).toBe(
      'auth.errors.turnstile_unavailable'
    );
    expect(turnstileErrorKey(new Error('network'), true)).toBeNull();
  });
});

describe('turnstileHeaders', () => {
  it('carries the token in the header the API reads, and nothing without one', () => {
    expect(turnstileHeaders('tok')).toEqual({ headers: { [TURNSTILE_TOKEN_HEADER]: 'tok' } });
    expect(TURNSTILE_TOKEN_HEADER).toBe('X-LIA-Turnstile-Response');
    expect(turnstileHeaders(null)).toBeUndefined();
  });
});

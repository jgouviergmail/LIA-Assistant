/**
 * The one thing this helper exists to guarantee: a REAL navigation.
 *
 * Every call site mocks `openChatDeepLink` and asserts the href it received —
 * a good oracle for WHAT is requested, and a blind one for HOW. If this
 * function ever degraded to `router.push`, those tests would stay green while
 * production silently went back to replaying the first deep link of a session
 * (ADR-192). So the door itself is pinned here, and only here.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';

import { chatDraftHref, chatIntentHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import { logger } from '@/lib/logger';

/** jsdom refuses a real navigation, so `assign` is replaced for the assertion. */
function captureNavigation(): { calls: string[]; restore: () => void } {
  const calls: string[] = [];
  const original = window.location;
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: { ...original, assign: (href: string) => calls.push(href) },
  });
  return {
    calls,
    restore: () =>
      Object.defineProperty(window, 'location', {
        configurable: true,
        writable: true,
        value: original,
      }),
  };
}

describe('openChatDeepLink', () => {
  const spies: (() => void)[] = [];
  afterEach(() => {
    spies.splice(0).forEach(restore => restore());
    vi.restoreAllMocks();
  });

  it('hands the URL to the BROWSER, not to the client router', () => {
    const nav = captureNavigation();
    spies.push(nav.restore);

    openChatDeepLink('/fr/dashboard/chat?intent=Bonjour');

    expect(nav.calls).toEqual(['/fr/dashboard/chat?intent=Bonjour']);
  });

  it('passes the href through verbatim, encoding included', () => {
    // The chat page parses these params; a helper that re-encoded or dropped
    // one would corrupt exactly the request it was built to protect.
    const nav = captureNavigation();
    spies.push(nav.restore);

    const href = chatIntentHref('fr', 'Point 360° sur Paul Martin', {
      capability: 'person_overview',
      subject: 'Paul Martin',
    });
    openChatDeepLink(href);

    expect(nav.calls).toEqual([href]);
    expect(nav.calls[0]).toContain('capability=person_overview');
    expect(nav.calls[0]).toContain('subject=Paul%20Martin');
  });

  describe('refuses anything that is not an internal path', () => {
    // Same doctrine as `safe-navigation.ts`: guard the PRIMITIVE, so the
    // property no longer depends on every current and future caller
    // remembering it. Today all 13 sites pass `chatIntentHref`/`chatDraftHref`,
    // which can only produce `/{lng}/dashboard/chat…` — this keeps that true
    // for the fourteenth.
    it.each([
      ['an absolute URL to another origin', 'https://evil.example/steal'],
      ['a protocol-relative URL', '//evil.example/steal'],
      ['an executable scheme', 'javascript:alert(document.cookie)'],
      ['a backslash-smuggled host', '/\\evil.example'],
      ['an empty href', ''],
    ])('%s', (_label, href) => {
      const nav = captureNavigation();
      spies.push(nav.restore);
      vi.spyOn(logger, 'error').mockImplementation(() => undefined);

      openChatDeepLink(href);

      expect(nav.calls).toEqual([]);
      expect(logger.error).toHaveBeenCalled();
    });
  });

  it('carries a prefill the same way as a command', () => {
    // `?draft=` was the dangerous case in production: a prefill link returning
    // as a previous `?intent=` does not merely show the wrong text, it EXECUTES
    // a request the user never made on that click.
    const nav = captureNavigation();
    spies.push(nav.restore);

    openChatDeepLink(chatDraftHref('de', 'Ruf Paul Martin an'));

    expect(nav.calls).toEqual(['/de/dashboard/chat?draft=Ruf%20Paul%20Martin%20an']);
  });
});

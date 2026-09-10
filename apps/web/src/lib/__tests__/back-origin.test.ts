/**
 * Where a screen was reached FROM (owner, 2026-09-10).
 *
 * Several doors lead to the meetings pages — the header, the phone menu, a
 * minutes card in the chat, a recorder toast, the settings section, a slash
 * command — and the list had no way back at all. The browser's own history is
 * not the answer: it dies on a reload, and after deleting a meeting it points
 * at a page that no longer exists.
 *
 * So the origin travels in the URL, and it travels as a TOKEN — never as a
 * URL, which would be an open redirect the moment somebody types one. The
 * vocabulary is the dashboard's own destination table, so a token that is not
 * a real screen cannot exist, and the label a back button shows is the very
 * word the header shows for that screen.
 */

import { describe, expect, it } from 'vitest';

import { backDestination, originFromPathname, withOrigin } from '@/lib/back-origin';
import { DASHBOARD_DESTINATIONS } from '@/lib/dashboard-nav';

describe('originFromPathname', () => {
  it('names the dashboard root', () => {
    expect(originFromPathname('/fr/dashboard')).toBe('');
    expect(originFromPathname('/fr/dashboard/')).toBe('');
  });

  it.each([
    ['/fr/dashboard/chat', 'chat'],
    ['/en/dashboard/relations', 'relations'],
    ['/de/dashboard/notifications', 'notifications'],
    ['/zh/dashboard/settings', 'settings'],
    ['/it/dashboard/faq', 'faq'],
  ])('names %s as %s', (pathname, expected) => {
    expect(originFromPathname(pathname)).toBe(expected);
  });

  it('names the destination of a NESTED route, not the nested page', () => {
    // `/dashboard/settings?section=meetings` and `/dashboard/spaces/<id>` are
    // both "the screen I was on".
    expect(originFromPathname('/fr/dashboard/settings/anything')).toBe('settings');
  });

  it('answers null for a screen that is not a destination', () => {
    // Deliberate: the token vocabulary is closed. A back button pointing at
    // `/dashboard/spaces` would need that screen in the table first.
    expect(originFromPathname('/fr/dashboard/spaces')).toBeNull();
  });

  it('answers null outside the dashboard', () => {
    expect(originFromPathname('/fr/blog')).toBeNull();
    expect(originFromPathname('/')).toBeNull();
    expect(originFromPathname(null)).toBeNull();
  });

  it('does not mistake a longer segment for a destination', () => {
    expect(originFromPathname('/fr/dashboard/chatterbox')).toBeNull();
  });
});

describe('backDestination', () => {
  it('resolves a token to its route and the header’s own word', () => {
    expect(backDestination('relations')).toEqual({
      href: '/dashboard/relations',
      labelKey: 'navigation.relations',
    });
  });

  it('resolves the dashboard root', () => {
    expect(backDestination('')).toEqual({
      href: '/dashboard',
      labelKey: 'navigation.dashboard',
    });
  });

  it('falls back to the chat when no origin travelled', () => {
    // Owner's arbitration: « si pas possible alors retour chat par défaut ».
    expect(backDestination(null).href).toBe('/dashboard/chat');
    expect(backDestination(undefined).href).toBe('/dashboard/chat');
  });

  it('falls back to the chat for a token nobody declared', () => {
    expect(backDestination('https://evil.example.com').href).toBe('/dashboard/chat');
    expect(backDestination('../../admin').href).toBe('/dashboard/chat');
  });

  it('never returns anything but a dashboard route', () => {
    for (const candidate of ['', 'chat', 'faq', 'nonsense', '//evil.com', null]) {
      expect(backDestination(candidate).href.startsWith('/dashboard')).toBe(true);
    }
  });

  it('knows every destination the header can show', () => {
    for (const { segment, labelKey } of DASHBOARD_DESTINATIONS) {
      expect(backDestination(segment)).toEqual({
        href: segment ? `/dashboard/${segment}` : '/dashboard',
        labelKey,
      });
    }
  });
});

describe('withOrigin', () => {
  it('appends the origin as a query parameter', () => {
    expect(withOrigin('/dashboard/meetings', 'chat')).toBe('/dashboard/meetings?from=chat');
  });

  it('encodes the dashboard root as an explicit, non-empty token', () => {
    // An empty `?from=` is indistinguishable from no origin at all.
    expect(withOrigin('/dashboard/meetings', '')).toBe('/dashboard/meetings?from=dashboard');
  });

  it('leaves the route alone when there is no origin', () => {
    expect(withOrigin('/dashboard/meetings', null)).toBe('/dashboard/meetings');
  });

  it('does not carry an origin equal to the destination', () => {
    // Coming back to where you already are is not a way back.
    expect(withOrigin('/dashboard/meetings', 'meetings')).toBe('/dashboard/meetings');
  });

  it('preserves a query the route already carries', () => {
    expect(withOrigin('/dashboard/meetings?x=1', 'chat')).toBe('/dashboard/meetings?x=1&from=chat');
  });

  it('round-trips through backDestination', () => {
    const href = withOrigin('/dashboard/meetings', 'relations');
    const token = new URL(href, 'https://x').searchParams.get('from');
    expect(backDestination(token).href).toBe('/dashboard/relations');
  });

  it('round-trips the dashboard root token', () => {
    const href = withOrigin('/dashboard/meetings', '');
    const token = new URL(href, 'https://x').searchParams.get('from');
    expect(backDestination(token).href).toBe('/dashboard');
  });
});

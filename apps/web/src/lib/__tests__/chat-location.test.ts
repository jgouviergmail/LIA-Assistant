/**
 * The annex the chat shows, read where the chat reads it: its URL (ADR-378
 * amendment 2026-11-14). A meeting recorded from the header while an annex is
 * open returns its minutes there; anywhere else, to Main.
 */

import { describe, expect, it } from 'vitest';

import { chatDiscussionOnScreen } from '@/lib/chat-location';

const ANNEX = '0f8fad5b-d9cb-469f-a165-70867728950e';

describe('chatDiscussionOnScreen', () => {
  it.each(['/dashboard/chat', '/en/dashboard/chat', '/zh/dashboard/chat/', '/fr/dashboard/chat'])(
    'reads the annex the chat at %s shows',
    pathname => {
      expect(chatDiscussionOnScreen({ pathname, search: `?conversation=${ANNEX}` })).toBe(ANNEX);
    }
  );

  it('normalises the id the way the chat reads it', () => {
    expect(
      chatDiscussionOnScreen({
        pathname: '/dashboard/chat',
        search: `?conversation=${ANNEX.toUpperCase()}&intent=x`,
      })
    ).toBe(ANNEX);
  });

  it('reads Main, which carries no parameter, as no annex', () => {
    expect(chatDiscussionOnScreen({ pathname: '/dashboard/chat', search: '' })).toBeNull();
  });

  it.each([
    ['/dashboard/meetings', `?conversation=${ANNEX}`],
    ['/en/dashboard/chat/history', `?conversation=${ANNEX}`],
    ['/dashboard/chatroom', `?conversation=${ANNEX}`],
  ])('reads no discussion on another page (%s)', (pathname, search) => {
    expect(chatDiscussionOnScreen({ pathname, search })).toBeNull();
  });

  it.each(['not-an-id', '', `${ANNEX}x`])(
    'refuses a parameter that is no discussion id (%s)',
    id => {
      expect(
        chatDiscussionOnScreen({ pathname: '/dashboard/chat', search: `?conversation=${id}` })
      ).toBeNull();
    }
  );
});

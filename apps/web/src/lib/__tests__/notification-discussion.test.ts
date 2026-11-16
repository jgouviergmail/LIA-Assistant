/**
 * Which discussion a notification went to, and what the person calls it
 * (ADR-378 amendment 2026-11-14): a return comes back to the discussion its act
 * was begun in, and the server names that discussion only when it is an annex.
 */

import { describe, expect, it } from 'vitest';

import { discussionTitleIn, notificationElsewhere } from '@/lib/notification-discussion';
import type { ConversationCataloguePage, ConversationSummary } from '@/types/conversation';

function row(overrides: Partial<ConversationSummary>): ConversationSummary {
  return {
    id: 'main-1',
    user_id: 'user-1',
    kind: 'main',
    revision: 0,
    title: null,
    message_count: 3,
    total_tokens: 10,
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-01T10:00:00Z',
    ...overrides,
  };
}

const page: ConversationCataloguePage = {
  items: [
    row({}),
    row({ id: 'annex-1', kind: 'secondary', title: 'Travaux' }),
    row({ id: 'annex-2', kind: 'secondary', title: null }),
  ],
  total_count: 3,
  offset: 0,
  limit: 20,
};

const onMain = { id: 'main-1', isMain: true } as const;
const onAnnex = (id: string) => ({ id, isMain: false });
const annex = (id: string) => ({ kind: 'discussion', id }) as const;

describe('notificationElsewhere', () => {
  it('names an annex that is not the discussion on screen', () => {
    expect(notificationElsewhere({ conversation_id: 'annex-1' }, onMain)).toEqual(annex('annex-1'));
    expect(notificationElsewhere({ conversation_id: 'annex-1' }, onAnnex('annex-2'))).toEqual(
      annex('annex-1')
    );
  });

  it('names nothing for the discussion on screen', () => {
    expect(notificationElsewhere({ conversation_id: 'annex-1' }, onAnnex('annex-1'))).toBeNull();
  });

  it('names Main for a notification naming no discussion, seen from an annex', () => {
    expect(notificationElsewhere(undefined, onAnnex('annex-1'))).toEqual({ kind: 'main' });
    expect(notificationElsewhere({ conversation_id: '' }, onAnnex('annex-1'))).toEqual({
      kind: 'main',
    });
    expect(notificationElsewhere({ conversation_id: 42 }, onAnnex('annex-1'))).toEqual({
      kind: 'main',
    });
  });

  it('names nothing for a notification to Main seen from Main', () => {
    expect(notificationElsewhere(undefined, onMain)).toBeNull();
    expect(notificationElsewhere({}, { id: null, isMain: true })).toBeNull();
  });

  it('names the annex while Main has no record yet', () => {
    expect(notificationElsewhere({ conversation_id: 'annex-1' }, { id: null, isMain: true })).toEqual(
      annex('annex-1')
    );
  });
});

describe('discussionTitleIn', () => {
  it('calls Main by its translated name and an annex by its title', () => {
    expect(discussionTitleIn(page, 'main-1', 'Principale')).toBe('Principale');
    expect(discussionTitleIn(page, 'annex-1', 'Principale')).toBe('Travaux');
  });

  it('has no name for an annex without a title, one off the page, or an unread catalogue', () => {
    expect(discussionTitleIn(page, 'annex-2', 'Principale')).toBeNull();
    expect(discussionTitleIn(page, 'annex-9', 'Principale')).toBeNull();
    expect(discussionTitleIn(undefined, 'annex-1', 'Principale')).toBeNull();
  });
});

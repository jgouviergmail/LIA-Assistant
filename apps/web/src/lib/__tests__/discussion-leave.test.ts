import { describe, expect, it, vi } from 'vitest';

import type { DiscussionSearchResult } from '@/hooks/useConversation';
import { discussionReach, leavingCancelsTurn } from '@/lib/discussion-leave';
import type {
  ConversationCatalogueConfig,
  ConversationCataloguePage,
  ConversationSummary,
} from '@/types/conversation';

function rules(backgroundRuns: boolean): ConversationCatalogueConfig {
  return {
    creation_enabled: true,
    background_runs_enabled: backgroundRuns,
    title_max_length: 500,
    title_pattern: '^.*$',
    offset_max: 1000,
    page_default_limit: 20,
    page_max_limit: 50,
  };
}

function summary(overrides: Partial<ConversationSummary> = {}): ConversationSummary {
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

function page(total: number): ConversationCataloguePage {
  return { items: [], total_count: total, offset: 0, limit: 20 };
}

function result(overrides: Partial<DiscussionSearchResult> = {}): DiscussionSearchResult {
  return {
    message_id: 'm-1',
    role: 'user',
    content: 'le devis',
    created_at: '2026-11-02T10:00:00Z',
    conversation_id: 'annex-1',
    conversation_kind: 'secondary',
    conversation_title: 'Travaux',
    conversation_revision: 2,
    ...overrides,
  };
}

describe('leavingCancelsTurn', () => {
  it('lets a quiet discussion go, whatever the deployment', () => {
    expect(leavingCancelsTurn(false, rules(false))).toBe(false);
    expect(leavingCancelsTurn(false, rules(true))).toBe(false);
    expect(leavingCancelsTurn(false, undefined)).toBe(false);
  });

  it('lets a running turn go on in the background where the deployment runs it there', () => {
    expect(leavingCancelsTurn(true, rules(true))).toBe(false);
  });

  it('holds a running turn where nothing runs in the background', () => {
    expect(leavingCancelsTurn(true, rules(false))).toBe(true);
  });

  it('holds a running turn when the rules are not known', () => {
    expect(leavingCancelsTurn(true, undefined)).toBe(true);
  });
});

describe('discussionReach', () => {
  const open = vi.fn<(id: string | null) => void>();

  it('names the discussion on screen, and none for Main before its first message', () => {
    const switcher = { rules: rules(true), page: page(2) };
    expect(discussionReach({ switcher, current: summary(), typing: false, open }).currentId).toBe(
      'main-1'
    );
    expect(discussionReach({ switcher, current: null, typing: false, open }).currentId).toBeNull();
  });

  it('counts the other discussions without the one on screen', () => {
    const one = { rules: rules(true), page: page(1) };
    expect(
      discussionReach({ switcher: one, current: summary(), typing: false, open }).hasOtherDiscussions
    ).toBe(false);
    // Main not created yet: the one listed discussion is another one.
    expect(
      discussionReach({ switcher: one, current: null, typing: false, open }).hasOtherDiscussions
    ).toBe(true);
    const two = { rules: rules(true), page: page(2) };
    expect(
      discussionReach({ switcher: two, current: summary(), typing: false, open }).hasOtherDiscussions
    ).toBe(true);
  });

  it('counts an unread catalogue as other discussions: the search is a read', () => {
    const unread = { rules: rules(true) };
    expect(
      discussionReach({ switcher: unread, current: summary(), typing: false, open })
        .hasOtherDiscussions
    ).toBe(true);
  });

  it('reaches no other discussion on an API that publishes no catalogue', () => {
    const reach = discussionReach({ switcher: undefined, current: summary(), typing: false, open });
    expect(reach.hasOtherDiscussions).toBe(false);
    expect(reach.openResult).toBeUndefined();
  });

  it('opens an annex by its identity, and Main as Main', () => {
    open.mockClear();
    const reach = discussionReach({
      switcher: { rules: rules(false), page: page(2) },
      current: summary(),
      typing: false,
      open,
    });
    reach.openResult?.(result());
    reach.openResult?.(result({ conversation_id: 'main-1', conversation_kind: 'main' }));
    expect(open.mock.calls).toEqual([['annex-1'], [null]]);
  });

  it('opens nothing while leaving would cancel the running turn', () => {
    const held = discussionReach({
      switcher: { rules: rules(false), page: page(2) },
      current: summary(),
      typing: true,
      open,
    });
    expect(held.openResult).toBeUndefined();
    const background = discussionReach({
      switcher: { rules: rules(true), page: page(2) },
      current: summary(),
      typing: true,
      open,
    });
    expect(background.openResult).toBeDefined();
  });
});

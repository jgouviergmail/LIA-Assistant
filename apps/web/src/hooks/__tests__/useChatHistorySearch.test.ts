/**
 * useChatHistorySearch — feature state machine tests (QW-2, lot 12).
 *
 * Covers the client filter (accent-insensitive), the server-search
 * availability gating, panel pagination and error state, the jump/return
 * history-view transitions (keyset +1ms cursor), the send guard, and the
 * search across discussions: a result of ANOTHER discussion opens it, and the
 * arriving discussion jumps to the message once its history is loaded.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import { useChatHistorySearch } from '../useChatHistorySearch';
import type {
  ConversationPage,
  DiscussionSearchPage,
  DiscussionSearchResult,
} from '../useConversation';
import { SEARCH_DEBOUNCE_MS } from '@/lib/constants';
import {
  resetDiscussionJumpForTests,
  requestDiscussionJump,
  takeDiscussionJump,
} from '@/lib/discussion-jump';
import type { Message } from '@/types/chat';

const HERE = 'main-1';
const THERE = 'annex-1';

function message(overrides: Partial<Message> & Pick<Message, 'id' | 'content'>): Message {
  return {
    role: 'assistant',
    timestamp: new Date('2026-07-01T10:00:00Z'),
    ...overrides,
  } as Message;
}

function searchRow(overrides: Partial<DiscussionSearchResult> = {}): DiscussionSearchResult {
  return {
    message_id: 'row-1',
    role: 'assistant',
    content: 'la réunion de mardi',
    created_at: '2026-06-01T10:00:00.000Z',
    conversation_id: HERE,
    conversation_kind: 'main',
    conversation_title: null,
    conversation_revision: 0,
    ...overrides,
  };
}

function page(messages: Message[], hasMore = false): ConversationPage {
  return { messages, hasMore, nextCursor: hasMore ? 'cursor' : null };
}

describe('useChatHistorySearch', () => {
  const messages = [
    message({ id: 'm1', content: 'On planifie la réunion de mardi' }),
    message({ id: 'm2', content: 'Voici la météo du jour' }),
  ];

  type SearchFn = (q: string, c?: string) => Promise<DiscussionSearchPage>;
  type OlderFn = (c: string) => Promise<ConversationPage>;
  type PageFn = () => Promise<ConversationPage>;

  let searchDiscussions: ReturnType<typeof vi.fn<SearchFn>>;
  let loadOlderMessages: ReturnType<typeof vi.fn<OlderFn>>;
  let loadConversationPage: ReturnType<typeof vi.fn<PageFn>>;
  let setMessages: ReturnType<typeof vi.fn<(messages: Message[]) => void>>;
  let setHasMoreOlder: ReturnType<typeof vi.fn<(hasMore: boolean) => void>>;
  let setOldestCursor: ReturnType<typeof vi.fn<(cursor: string | null) => void>>;
  let openDiscussion: ReturnType<typeof vi.fn<(row: DiscussionSearchResult) => void>>;

  interface Overrides {
    isTyping?: boolean;
    hasMoreOlder?: boolean;
    hasOtherDiscussions?: boolean;
    historyReady?: boolean;
    canOpen?: boolean;
    currentDiscussionId?: string;
  }

  function renderSearch(initial: Overrides = {}) {
    return renderHook(
      (props: Overrides) =>
        useChatHistorySearch({
          messages,
          isTyping: props.isTyping ?? false,
          hasMoreOlder: props.hasMoreOlder ?? true,
          hasOtherDiscussions: props.hasOtherDiscussions ?? false,
          historyReady: props.historyReady ?? true,
          currentDiscussionId: props.currentDiscussionId ?? HERE,
          openDiscussion: props.canOpen === false ? undefined : openDiscussion,
          searchDiscussions,
          loadOlderMessages,
          loadConversationPage,
          setMessages,
          setHasMoreOlder,
          setOldestCursor,
        }),
      { initialProps: initial }
    );
  }

  beforeEach(() => {
    vi.useFakeTimers();
    resetDiscussionJumpForTests();
    searchDiscussions = vi.fn<SearchFn>().mockResolvedValue({
      rows: [searchRow()],
      hasMore: false,
      nextCursor: null,
    });
    loadOlderMessages = vi
      .fn<OlderFn>()
      .mockResolvedValue(page([message({ id: 'old', content: 'x' })]));
    loadConversationPage = vi
      .fn<PageFn>()
      .mockResolvedValue(page([message({ id: 'fresh', content: 'y' })]));
    setMessages = vi.fn<(messages: Message[]) => void>();
    setHasMoreOlder = vi.fn<(hasMore: boolean) => void>();
    setOldestCursor = vi.fn<(cursor: string | null) => void>();
    openDiscussion = vi.fn<(row: DiscussionSearchResult) => void>();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const settleDebounce = async () => {
    await act(async () => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS + 10);
    });
  };

  it('filters loaded messages accent-insensitively and counts matches', () => {
    const { result } = renderSearch();

    act(() => result.current.setSearchQuery('reunion'));

    expect(result.current.displayedMessages.map(m => m.id)).toEqual(['m1']);
    expect(result.current.loadedMatchCount).toBe(1);
  });

  it('offers the server search from 2 chars, when there is history or another discussion to search', async () => {
    const { result } = renderSearch();

    act(() => result.current.setSearchQuery('r'));
    await settleDebounce();
    expect(result.current.serverSearchAvailable).toBe(false);

    act(() => result.current.setSearchQuery('reunion'));
    await settleDebounce();
    expect(result.current.serverSearchAvailable).toBe(true);

    // Everything loaded, and no other discussion: the server has nothing more.
    const { result: complete } = renderSearch({ hasMoreOlder: false });
    act(() => complete.current.setSearchQuery('reunion'));
    await settleDebounce();
    expect(complete.current.serverSearchAvailable).toBe(false);

    // Everything loaded here, but another discussion may hold the words.
    const { result: others } = renderSearch({ hasMoreOlder: false, hasOtherDiscussions: true });
    act(() => others.current.setSearchQuery('reunion'));
    await settleDebounce();
    expect(others.current.serverSearchAvailable).toBe(true);
  });

  it('runs the server search and paginates with the opaque cursor', async () => {
    searchDiscussions
      .mockResolvedValueOnce({
        rows: [searchRow({ message_id: 'r1' })],
        hasMore: true,
        nextCursor: 'c1',
      })
      .mockResolvedValueOnce({
        rows: [searchRow({ message_id: 'r2' })],
        hasMore: false,
        nextCursor: null,
      });
    const { result } = renderSearch();
    act(() => result.current.setSearchQuery('reunion'));
    await settleDebounce();

    await act(async () => {
      await result.current.runServerSearch();
    });
    expect(result.current.panelOpen).toBe(true);
    expect(result.current.serverResults.map(r => r.message_id)).toEqual(['r1']);
    expect(result.current.serverHasMore).toBe(true);

    await act(async () => {
      await result.current.loadMoreServerResults();
    });
    expect(searchDiscussions).toHaveBeenLastCalledWith('reunion', 'c1');
    expect(result.current.serverResults.map(r => r.message_id)).toEqual(['r1', 'r2']);
  });

  it('surfaces a transport failure as an error state', async () => {
    searchDiscussions.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderSearch();
    act(() => result.current.setSearchQuery('reunion'));
    await settleDebounce();

    await act(async () => {
      await result.current.runServerSearch();
    });

    expect(result.current.serverError).toBe(true);
    expect(result.current.panelOpen).toBe(true);
  });

  it('invalidates open results when the debounced term changes', async () => {
    const { result } = renderSearch();
    act(() => result.current.setSearchQuery('reunion'));
    await settleDebounce();
    await act(async () => {
      await result.current.runServerSearch();
    });
    expect(result.current.serverResults).toHaveLength(1);

    act(() => result.current.setSearchQuery('pizza'));
    await settleDebounce();

    expect(result.current.panelOpen).toBe(false);
    expect(result.current.serverResults).toHaveLength(0);
  });

  it('jumps to a result of this discussion: +1ms keyset cursor, history view, retained highlight', async () => {
    const { result } = renderSearch();
    act(() => result.current.setSearchQuery('reunion'));
    await settleDebounce();

    await act(async () => {
      await result.current.jumpToResult(searchRow({ created_at: '2026-06-01T10:00:00.000Z' }));
    });

    expect(loadOlderMessages).toHaveBeenCalledWith('2026-06-01T10:00:00.001Z');
    expect(setMessages).toHaveBeenCalledWith([expect.objectContaining({ id: 'old' })]);
    expect(result.current.historyView).toBe(true);
    expect(result.current.searchQuery).toBe('');
    expect(result.current.highlightTerm).toBe('reunion');
    expect(openDiscussion).not.toHaveBeenCalled();
  });

  it('opens the discussion holding a result found elsewhere, and leaves it the jump', async () => {
    const { result } = renderSearch();
    act(() => result.current.setSearchQuery('reunion'));
    await settleDebounce();
    await act(async () => {
      await result.current.runServerSearch();
    });
    const there = searchRow({ conversation_id: THERE, conversation_kind: 'secondary' });

    await act(async () => {
      await result.current.jumpToResult(there);
    });

    expect(openDiscussion).toHaveBeenCalledWith(there);
    expect(loadOlderMessages).not.toHaveBeenCalled();
    expect(result.current.panelOpen).toBe(false);
    expect(takeDiscussionJump(THERE)).toEqual({
      conversationId: THERE,
      createdAt: there.created_at,
      term: 'reunion',
    });
  });

  it('leaves a result found elsewhere alone when the discussion cannot be left now', async () => {
    const { result } = renderSearch({ canOpen: false });

    await act(async () => {
      await result.current.jumpToResult(searchRow({ conversation_id: THERE }));
    });

    expect(loadOlderMessages).not.toHaveBeenCalled();
    expect(takeDiscussionJump(THERE)).toBeNull();
  });

  it('arrives at the message once its history is loaded, marking the words searched', async () => {
    requestDiscussionJump({ conversationId: HERE, createdAt: '2026-06-01T10:00:00.000Z', term: 'devis' });
    const view = renderSearch({ historyReady: false });

    await act(async () => {});
    expect(loadOlderMessages).not.toHaveBeenCalled();

    view.rerender({ historyReady: true });
    await act(async () => {});

    expect(loadOlderMessages).toHaveBeenCalledWith('2026-06-01T10:00:00.001Z');
    expect(view.result.current.historyView).toBe(true);
    expect(view.result.current.highlightTerm).toBe('devis');
    expect(takeDiscussionJump(HERE)).toBeNull();
  });

  it('never takes a jump left for another discussion', async () => {
    requestDiscussionJump({ conversationId: THERE, createdAt: '2026-06-01T10:00:00.000Z', term: 'devis' });

    renderSearch();
    await act(async () => {});

    expect(loadOlderMessages).not.toHaveBeenCalled();
    expect(takeDiscussionJump(THERE)?.conversationId).toBe(THERE);
  });

  it('ignores jumps within this discussion while a stream is active', async () => {
    const { result } = renderSearch({ isTyping: true });

    await act(async () => {
      await result.current.jumpToResult(searchRow());
    });

    expect(loadOlderMessages).not.toHaveBeenCalled();
    expect(result.current.historyView).toBe(false);
  });

  it('opens another discussion while a turn runs here, when this one may be left', async () => {
    // The caller passes `openDiscussion` only when leaving cancels nothing
    // (`leavingCancelsTurn`): the turn goes on in the background.
    const { result } = renderSearch({ isTyping: true });
    const there = searchRow({ conversation_id: THERE, conversation_kind: 'secondary' });

    await act(async () => {
      await result.current.jumpToResult(there);
    });

    expect(openDiscussion).toHaveBeenCalledWith(there);
    expect(loadOlderMessages).not.toHaveBeenCalled();
    expect(takeDiscussionJump(THERE)?.createdAt).toBe(there.created_at);
  });

  it('stays out of history view when the jump page comes back empty', async () => {
    loadOlderMessages.mockResolvedValueOnce(page([]));
    const { result } = renderSearch();

    await act(async () => {
      await result.current.jumpToResult(searchRow());
    });

    expect(setMessages).not.toHaveBeenCalled();
    expect(result.current.historyView).toBe(false);
  });

  it('returns to present: first page reloaded, highlight cleared', async () => {
    const { result } = renderSearch();
    act(() => result.current.setSearchQuery('reunion'));
    await settleDebounce();
    await act(async () => {
      await result.current.jumpToResult(searchRow());
    });

    await act(async () => {
      await result.current.returnToPresent();
    });

    expect(loadConversationPage).toHaveBeenCalled();
    expect(setMessages).toHaveBeenLastCalledWith([expect.objectContaining({ id: 'fresh' })]);
    expect(result.current.historyView).toBe(false);
    expect(result.current.highlightTerm).toBe('');
  });

  it('ensurePresent is a no-op outside history view and restores it inside', async () => {
    const { result } = renderSearch();

    await act(async () => {
      await result.current.ensurePresent();
    });
    expect(loadConversationPage).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.jumpToResult(searchRow());
    });
    await act(async () => {
      await result.current.ensurePresent();
    });
    expect(loadConversationPage).toHaveBeenCalledTimes(1);
    expect(result.current.historyView).toBe(false);
  });
});

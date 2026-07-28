/**
 * useChatHistorySearch — feature state machine tests (QW-2).
 *
 * Covers the client filter (accent-insensitive), the server-search
 * availability gating, panel pagination and error state, the jump/return
 * history-view transitions (keyset +1ms cursor), and the send guard.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import { useChatHistorySearch } from '../useChatHistorySearch';
import type { ConversationMessage, ConversationPage, MessageSearchPage } from '../useConversation';
import { SEARCH_DEBOUNCE_MS } from '@/lib/constants';
import type { Message } from '@/types/chat';

function message(overrides: Partial<Message> & Pick<Message, 'id' | 'content'>): Message {
  return {
    role: 'assistant',
    timestamp: new Date('2026-07-01T10:00:00Z'),
    ...overrides,
  } as Message;
}

function searchRow(overrides: Partial<ConversationMessage>): ConversationMessage {
  return {
    id: 'row-1',
    role: 'assistant',
    content: 'la réunion de mardi',
    message_metadata: null,
    created_at: '2026-06-01T10:00:00.000Z',
    tokens_in: null,
    tokens_out: null,
    tokens_cache: null,
    cost_eur: null,
    google_api_requests: null,
    stt_provider: null,
    stt_audio_duration_seconds: null,
    stt_cost_eur: null,
    tts_provider: null,
    tts_model: null,
    tts_characters: null,
    tts_cost_eur: null,
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

  type SearchFn = (q: string, b?: string) => Promise<MessageSearchPage>;
  type OlderFn = (c: string) => Promise<ConversationPage>;
  type PageFn = () => Promise<ConversationPage>;

  let searchMessages: ReturnType<typeof vi.fn<SearchFn>>;
  let loadOlderMessages: ReturnType<typeof vi.fn<OlderFn>>;
  let loadConversationPage: ReturnType<typeof vi.fn<PageFn>>;
  let setMessages: ReturnType<typeof vi.fn<(messages: Message[]) => void>>;
  let setHasMoreOlder: ReturnType<typeof vi.fn<(hasMore: boolean) => void>>;
  let setOldestCursor: ReturnType<typeof vi.fn<(cursor: string | null) => void>>;

  function renderSearch(overrides: { isTyping?: boolean; hasMoreOlder?: boolean } = {}) {
    return renderHook(() =>
      useChatHistorySearch({
        messages,
        isTyping: overrides.isTyping ?? false,
        hasMoreOlder: overrides.hasMoreOlder ?? true,
        searchMessages,
        loadOlderMessages,
        loadConversationPage,
        setMessages,
        setHasMoreOlder,
        setOldestCursor,
      })
    );
  }

  beforeEach(() => {
    vi.useFakeTimers();
    searchMessages = vi.fn<SearchFn>().mockResolvedValue({
      rows: [searchRow({})],
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

  it('offers the server search only from 2 chars and when older history exists', async () => {
    const { result } = renderSearch();

    act(() => result.current.setSearchQuery('r'));
    await settleDebounce();
    expect(result.current.serverSearchAvailable).toBe(false);

    act(() => result.current.setSearchQuery('reunion'));
    await settleDebounce();
    expect(result.current.serverSearchAvailable).toBe(true);

    const { result: complete } = renderSearch({ hasMoreOlder: false });
    act(() => complete.current.setSearchQuery('reunion'));
    await settleDebounce();
    expect(complete.current.serverSearchAvailable).toBe(false);
  });

  it('runs the server search and paginates with the keyset cursor', async () => {
    searchMessages
      .mockResolvedValueOnce({ rows: [searchRow({ id: 'r1' })], hasMore: true, nextCursor: 'c1' })
      .mockResolvedValueOnce({ rows: [searchRow({ id: 'r2' })], hasMore: false, nextCursor: null });
    const { result } = renderSearch();
    act(() => result.current.setSearchQuery('reunion'));
    await settleDebounce();

    await act(async () => {
      await result.current.runServerSearch();
    });
    expect(result.current.panelOpen).toBe(true);
    expect(result.current.serverResults.map(r => r.id)).toEqual(['r1']);
    expect(result.current.serverHasMore).toBe(true);

    await act(async () => {
      await result.current.loadMoreServerResults();
    });
    expect(searchMessages).toHaveBeenLastCalledWith('reunion', 'c1');
    expect(result.current.serverResults.map(r => r.id)).toEqual(['r1', 'r2']);
  });

  it('surfaces a transport failure as an error state', async () => {
    searchMessages.mockRejectedValueOnce(new Error('boom'));
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

  it('jumps to a result: +1ms keyset cursor, history view, retained highlight', async () => {
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
  });

  it('ignores jumps while a stream is active', async () => {
    const { result } = renderSearch({ isTyping: true });

    await act(async () => {
      await result.current.jumpToResult(searchRow({}));
    });

    expect(loadOlderMessages).not.toHaveBeenCalled();
    expect(result.current.historyView).toBe(false);
  });

  it('stays out of history view when the jump page comes back empty', async () => {
    loadOlderMessages.mockResolvedValueOnce(page([]));
    const { result } = renderSearch();

    await act(async () => {
      await result.current.jumpToResult(searchRow({}));
    });

    expect(setMessages).not.toHaveBeenCalled();
    expect(result.current.historyView).toBe(false);
  });

  it('returns to present: first page reloaded, highlight cleared', async () => {
    const { result } = renderSearch();
    act(() => result.current.setSearchQuery('reunion'));
    await settleDebounce();
    await act(async () => {
      await result.current.jumpToResult(searchRow({}));
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
      await result.current.jumpToResult(searchRow({}));
    });
    await act(async () => {
      await result.current.ensurePresent();
    });
    expect(loadConversationPage).toHaveBeenCalledTimes(1);
    expect(result.current.historyView).toBe(false);
  });
});

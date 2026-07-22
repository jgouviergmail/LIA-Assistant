/**
 * useChatHistorySearch — state machine of the chat history search (QW-2).
 *
 * Owns everything the feature needs so the chat page only wires props:
 * - instant client-side filter over the LOADED messages (accent/case
 *   -insensitive via `normalizeSearchText`, matching the server semantics);
 * - a debounced term driving the in-bubble highlight and the server-search
 *   availability (min 2 chars, mirrors the backend constraint);
 * - the server search panel (keyset-paginated dated results);
 * - the "history view": jumping to a result replaces the message list with
 *   the page ENDING at that message (keyset `before = created_at + 1ms`),
 *   clears the filter so the surrounding context shows, retains the term as
 *   highlight, and offers "back to present". Sending a message while viewing
 *   history must call `returnToPresent` first (arbitration #1) — the page
 *   wraps its send handler with `ensurePresent`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useDebounce } from '@/hooks/useDebounce';
import type {
  ConversationMessage,
  ConversationPage,
  MessageSearchPage,
} from '@/hooks/useConversation';
import { CHAT_SEARCH_MIN_CHARS, SEARCH_DEBOUNCE_MS } from '@/lib/constants';
import { logger } from '@/lib/logger';
import { normalizeSearchText } from '@/lib/utils';
import type { Message } from '@/types/chat';

export interface UseChatHistorySearchParams {
  messages: Message[];
  /** Blocks jumps while a stream is active (a jump would tear the live turn). */
  isTyping: boolean;
  /** Whether older, not-yet-loaded history exists (server search only makes
   *  sense when the loaded window is incomplete). */
  hasMoreOlder: boolean;
  searchMessages: (query: string, before?: string) => Promise<MessageSearchPage>;
  loadOlderMessages: (beforeCursor: string) => Promise<ConversationPage>;
  loadConversationPage: () => Promise<ConversationPage>;
  setMessages: (messages: Message[]) => void;
  setHasMoreOlder: (hasMore: boolean) => void;
  setOldestCursor: (cursor: string | null) => void;
}

export interface UseChatHistorySearchReturn {
  searchQuery: string;
  setSearchQuery: (value: string) => void;
  /** Term to highlight inside bubbles ('' when nothing should be marked). */
  highlightTerm: string;
  /** Loaded messages filtered by the instant client-side search. */
  displayedMessages: Message[];
  /** Number of loaded messages matching the query (0 when not searching). */
  loadedMatchCount: number;
  /** True when the "search entire history" affordance should be offered. */
  serverSearchAvailable: boolean;
  panelOpen: boolean;
  serverResults: ConversationMessage[];
  serverHasMore: boolean;
  serverLoading: boolean;
  serverError: boolean;
  runServerSearch: () => Promise<void>;
  loadMoreServerResults: () => Promise<void>;
  closePanel: () => void;
  /** True while the list shows a jumped-to point of history. */
  historyView: boolean;
  jumpToResult: (row: ConversationMessage) => Promise<void>;
  returnToPresent: () => Promise<void>;
  /** Awaited by the page's send wrapper: restores the present before a send
   *  while in history view (no-op otherwise). */
  ensurePresent: () => Promise<void>;
}

export function useChatHistorySearch(
  params: UseChatHistorySearchParams
): UseChatHistorySearchReturn {
  const {
    messages,
    isTyping,
    hasMoreOlder,
    searchMessages,
    loadOlderMessages,
    loadConversationPage,
    setMessages,
    setHasMoreOlder,
    setOldestCursor,
  } = params;

  const [searchQuery, setSearchQuery] = useState('');
  const debouncedQuery = useDebounce(searchQuery, SEARCH_DEBOUNCE_MS);

  const [panelOpen, setPanelOpen] = useState(false);
  const [serverResults, setServerResults] = useState<ConversationMessage[]>([]);
  const [serverHasMore, setServerHasMore] = useState(false);
  const [serverCursor, setServerCursor] = useState<string | null>(null);
  const [serverLoading, setServerLoading] = useState(false);
  const [serverError, setServerError] = useState(false);

  const [historyView, setHistoryView] = useState(false);
  const [retainedTerm, setRetainedTerm] = useState('');
  // Prevents overlapping jump/return page swaps (double-click, slow network).
  const navInFlightRef = useRef(false);

  // Instant filter over the loaded window — same normalization as the server.
  const normalizedQuery = normalizeSearchText(searchQuery.trim());
  const displayedMessages = useMemo(() => {
    if (!normalizedQuery) return messages;
    return messages.filter(msg => normalizeSearchText(msg.content).includes(normalizedQuery));
  }, [messages, normalizedQuery]);

  const loadedMatchCount = normalizedQuery ? displayedMessages.length : 0;

  const serverSearchAvailable =
    debouncedQuery.trim().length >= CHAT_SEARCH_MIN_CHARS && hasMoreOlder;

  // A new (debounced) term invalidates any open results — the panel reruns on
  // demand rather than firing a request per keystroke.
  useEffect(() => {
    setPanelOpen(false);
    setServerResults([]);
    setServerHasMore(false);
    setServerCursor(null);
    setServerError(false);
  }, [debouncedQuery]);

  const fetchServerPage = useCallback(
    async (before?: string) => {
      setServerLoading(true);
      setServerError(false);
      try {
        const page = await searchMessages(debouncedQuery.trim(), before);
        setServerResults(prev => (before ? [...prev, ...page.rows] : page.rows));
        setServerHasMore(page.hasMore);
        setServerCursor(page.nextCursor);
      } catch {
        // Transport error already logged by searchMessages — surface a state.
        setServerError(true);
      } finally {
        setServerLoading(false);
      }
    },
    [debouncedQuery, searchMessages]
  );

  const runServerSearch = useCallback(async () => {
    setPanelOpen(true);
    await fetchServerPage();
  }, [fetchServerPage]);

  const loadMoreServerResults = useCallback(async () => {
    if (!serverCursor || serverLoading) return;
    await fetchServerPage(serverCursor);
  }, [serverCursor, serverLoading, fetchServerPage]);

  const closePanel = useCallback(() => setPanelOpen(false), []);

  const applyPage = useCallback(
    (page: ConversationPage) => {
      setMessages(page.messages);
      setHasMoreOlder(page.hasMore);
      setOldestCursor(page.nextCursor);
    },
    [setMessages, setHasMoreOlder, setOldestCursor]
  );

  const jumpToResult = useCallback(
    async (row: ConversationMessage) => {
      if (isTyping || navInFlightRef.current) return;
      navInFlightRef.current = true;
      try {
        // Keyset `before` is strictly `<`: +1ms makes the clicked message the
        // newest (bottom) row of the fetched page.
        const cursor = new Date(new Date(row.created_at).getTime() + 1).toISOString();
        const page = await loadOlderMessages(cursor);
        if (page.messages.length === 0) {
          logger.warn('history_jump_empty_page', { cursor });
          return;
        }
        applyPage(page);
        setRetainedTerm(debouncedQuery.trim());
        setHistoryView(true);
        setSearchQuery('');
        setPanelOpen(false);
      } finally {
        navInFlightRef.current = false;
      }
    },
    [isTyping, loadOlderMessages, applyPage, debouncedQuery]
  );

  const returnToPresent = useCallback(async () => {
    if (navInFlightRef.current) return;
    navInFlightRef.current = true;
    try {
      const page = await loadConversationPage();
      applyPage(page);
      setHistoryView(false);
      setRetainedTerm('');
    } finally {
      navInFlightRef.current = false;
    }
  }, [loadConversationPage, applyPage]);

  const ensurePresent = useCallback(async () => {
    if (historyView) {
      await returnToPresent();
    }
  }, [historyView, returnToPresent]);

  // An emptied field clears the highlight IMMEDIATELY — the debounced value
  // must never resurrect a query the user just erased (or the one a jump
  // consumed). While typing, the debounced term drives the (expensive)
  // re-render of the bubbles.
  const highlightTerm = historyView
    ? retainedTerm
    : searchQuery.trim()
      ? debouncedQuery.trim()
      : '';

  return {
    searchQuery,
    setSearchQuery,
    highlightTerm,
    displayedMessages,
    loadedMatchCount,
    serverSearchAvailable,
    panelOpen,
    serverResults,
    serverHasMore,
    serverLoading,
    serverError,
    runServerSearch,
    loadMoreServerResults,
    closePanel,
    historyView,
    jumpToResult,
    returnToPresent,
    ensurePresent,
  };
}

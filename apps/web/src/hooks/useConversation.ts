import { useState, useCallback, useEffect, useRef } from 'react';
import { apiClient } from '@/lib/api-client';
import { Message } from '@/types/chat';
import { useAuth } from '@/hooks/useAuth';
import { logger } from '@/lib/logger';
import { useLoggingContext } from '@/lib/logging-context';

/** Page size requested from /conversations/me/messages.
 *
 * Used for both the initial load and each scroll-up fetch. Should stay aligned
 * with the backend default ``CONVERSATION_HISTORY_DEFAULT_LIMIT`` (configured
 * via env, see ``src/core/config/advanced.py`` → ``conversation_history_default_limit``).
 * The backend still enforces ``CONVERSATION_HISTORY_MAX_LIMIT`` as a hard cap,
 * so an over-shoot from the client is harmless but wastes the round-trip.
 */
const CONVERSATION_PAGE_SIZE = 50;

/**
 * Hook for managing conversation state and persistence
 */

export interface Conversation {
  id: string;
  user_id: string;
  title: string | null;
  message_count: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  message_metadata: Record<string, unknown> | null; // API uses Pydantic alias "message_metadata"
  created_at: string;
  tokens_in: number | null;
  tokens_out: number | null;
  tokens_cache: number | null;
  cost_eur: number | null;
  google_api_requests: number | null;
  // Per-message STT cost (only for user messages produced by a remote
  // transcription provider). All NULL for assistant messages and for typed
  // text / local-Sherpa user messages.
  stt_provider: string | null;
  stt_audio_duration_seconds: number | null;
  stt_cost_eur: number | null;
  // Per-message TTS cost (only for assistant messages synthesised by a
  // paid TTS provider — Edge stays NULL). Mirror of STT pattern.
  tts_provider: string | null;
  tts_model: string | null;
  tts_characters: number | null;
  tts_cost_eur: number | null;
}

export interface ConversationTotals {
  conversation_id: string;
  total_tokens_in: number;
  total_tokens_out: number;
  total_tokens_cache: number;
  total_cost_eur: number;
  total_google_api_requests: number;
  // Context-usage pill (2026-05): current checkpoint token footprint vs
  // dynamic compaction threshold. Null when no checkpoint exists yet.
  context_tokens?: number | null;
  context_threshold?: number | null;
}

/** Result of a single page fetch from /conversations/me/messages.
 *
 * ``hasMore`` and ``nextCursor`` come straight from the backend response and
 * drive scroll-up pagination. ``messages`` are already in display order
 * (oldest → newest, ready to render without further sorting).
 */
export interface ConversationPage {
  messages: Message[];
  hasMore: boolean;
  /** ISO-8601 timestamp of the oldest message in this page. Pass it back as
   *  ``before`` on the next call to retrieve older messages. ``null`` once
   *  the start of the conversation has been reached.
   */
  nextCursor: string | null;
}

export interface UseConversationReturn {
  conversation: Conversation | null;
  isLoading: boolean;
  /** True while a scroll-up fetch is in flight. Use to disable the loader and
   *  prevent overlapping requests when the user scrolls fast. */
  isLoadingOlder: boolean;
  /** Initial page load with pagination metadata. Use this on first mount so
   *  the caller knows whether more history exists. */
  loadConversationPage: () => Promise<ConversationPage>;
  /** Fetch the next older page using a keyset cursor. ``beforeCursor`` is the
   *  ``nextCursor`` from the previous response. No-op (returns an empty page
   *  with ``hasMore=false``) if a fetch is already in flight. */
  loadOlderMessages: (beforeCursor: string) => Promise<ConversationPage>;
  loadConversationTotals: () => Promise<ConversationTotals | null>;
  resetConversation: () => Promise<void>;
}

export const useConversation = (): UseConversationReturn => {
  const { user } = useAuth();
  const { withContext } = useLoggingContext();
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingOlder, setIsLoadingOlder] = useState(false);
  // Mutex ref guarding overlapping scroll-up fetches. ``setIsLoadingOlder``
  // alone races with rapid scroll because React state updates are async —
  // the ref takes effect immediately so two near-simultaneous scroll events
  // produce a single API call.
  const isLoadingOlderRef = useRef(false);

  /**
   * Load current conversation metadata
   */
  const loadConversation = useCallback(async () => {
    if (!user) {
      return null;
    }

    try {
      const response = await apiClient.get<Conversation>('/conversations/me');
      setConversation(response || null);
      return response;
    } catch (error) {
      logger.error(
        'conversation_load_failed',
        error as Error,
        withContext({
          component: 'useConversation',
          userId: user.id,
        })
      );
      return null;
    }
  }, [user, withContext]);

  /**
   * Map an API message row to the UI ``Message`` shape.
   *
   * Shared between the initial page load and scroll-up pagination.
   */
  const toUiMessage = useCallback(
    (msg: ConversationMessage): Message => ({
      id: msg.id,
      content: msg.content,
      role: msg.role,
      timestamp: new Date(msg.created_at),
      // Assistant messages don't have avatar
      // User messages use profile picture if available
      avatar: msg.role === 'user' ? user?.picture_url || undefined : undefined,
      // Token usage and cost from backend (snake_case -> camelCase)
      tokensIn: msg.tokens_in ?? undefined,
      tokensOut: msg.tokens_out ?? undefined,
      tokensCache: msg.tokens_cache ?? undefined,
      costEur: msg.cost_eur ?? undefined,
      googleApiRequests: msg.google_api_requests ?? undefined,
      // Per-message STT cost (remote-STT user messages only). The
      // ``source: 'voice'`` flag is what gates the 🎤 badge in
      // ChatMessage; we set it from `stt_provider` (and mirror the
      // duration into ``audioDurationSeconds`` for back-compat with the
      // pre-existing voice indicator).
      ...(msg.stt_provider ? { source: 'voice' as const } : {}),
      sttProvider: msg.stt_provider ?? null,
      sttAudioDurationSeconds: msg.stt_audio_duration_seconds ?? null,
      sttCostEur: msg.stt_cost_eur ?? null,
      audioDurationSeconds: msg.stt_audio_duration_seconds ?? undefined,
      // Per-message TTS cost (assistant bubble badge — paid providers only).
      ttsProvider: msg.tts_provider ?? null,
      ttsModel: msg.tts_model ?? null,
      ttsCharacters: msg.tts_characters ?? null,
      ttsCostEur: msg.tts_cost_eur ?? null,
      // Message metadata (HITL responses, run_id, etc.) - API uses alias "message_metadata"
      metadata: msg.message_metadata ?? undefined,
      // AI-generated images persisted in message_metadata for history display
      generatedImages:
        (msg.message_metadata?.generated_images as { url: string; alt: string }[] | undefined) ??
        undefined,
      browserScreenshot:
        (msg.message_metadata?.browser_screenshot as { url: string; alt: string } | undefined) ??
        undefined,
    }),
    [user]
  );

  /**
   * Internal: fetch a single page of messages.
   *
   * Calls ``GET /conversations/me/messages`` with optional ``before`` keyset
   * cursor and returns ``{messages, hasMore, nextCursor}``. Messages come
   * back from the API newest-first and are reversed to display order
   * (oldest → newest) before being returned.
   */
  const fetchPage = useCallback(
    async (before?: string): Promise<ConversationPage> => {
      if (!user) {
        return { messages: [], hasMore: false, nextCursor: null };
      }

      try {
        const params: { limit: number; before?: string } = { limit: CONVERSATION_PAGE_SIZE };
        if (before) {
          params.before = before;
        }
        const response = await apiClient.get<{
          messages: ConversationMessage[];
          conversation_id: string;
          total_count: number;
          has_more: boolean;
          next_cursor: string | null;
        }>('/conversations/me/messages', { params });

        // Backend returns DESC (newest first). Reverse to display order.
        const messages: Message[] = response.messages.slice().reverse().map(toUiMessage);

        // First-page load is an operational event of interest (perf, user-issue
        // triage) — surface it at ``info``. Subsequent scroll-up pages are
        // higher-frequency and noisier, so log them at ``debug`` instead.
        const logMethod = before ? logger.debug : logger.info;
        logMethod(
          before ? 'conversation_older_loaded' : 'conversation_history_loaded',
          withContext({
            component: 'useConversation',
            messageCount: messages.length,
            conversationId: response.conversation_id,
            hasMore: response.has_more,
            before: before ?? null,
          })
        );

        return {
          messages,
          hasMore: response.has_more,
          nextCursor: response.next_cursor,
        };
      } catch (error: unknown) {
        // 404 is expected for new users without conversation - not an error
        if (error && typeof error === 'object' && 'response' in error) {
          const axiosError = error as { response?: { status?: number } };
          if (axiosError.response?.status === 404) {
            logger.debug(
              'conversation_not_found',
              withContext({
                component: 'useConversation',
                reason: 'no_conversation_yet',
              })
            );
            return { messages: [], hasMore: false, nextCursor: null };
          }
        }

        logger.error(
          before ? 'conversation_older_load_failed' : 'conversation_history_load_failed',
          error as Error,
          withContext({
            component: 'useConversation',
            userId: user.id,
            before: before ?? null,
          })
        );
        return { messages: [], hasMore: false, nextCursor: null };
      }
    },
    [user, withContext, toUiMessage]
  );

  /**
   * Load the newest page of conversation history with pagination metadata.
   *
   * Use on first mount or when refreshing the chat from scratch — the caller
   * gets ``hasMore`` and ``nextCursor`` so it can wire up scroll-up.
   */
  const loadConversationPage = useCallback(async (): Promise<ConversationPage> => {
    setIsLoading(true);
    try {
      return await fetchPage();
    } finally {
      setIsLoading(false);
    }
  }, [fetchPage]);

  /**
   * Fetch the next older page using a keyset cursor.
   *
   * ``beforeCursor`` is the ``nextCursor`` from the previous response. The
   * mutex ref guards against overlapping requests when the user scrolls
   * fast — a second concurrent call returns an empty page immediately.
   */
  const loadOlderMessages = useCallback(
    async (beforeCursor: string): Promise<ConversationPage> => {
      if (!user) {
        return { messages: [], hasMore: false, nextCursor: null };
      }
      if (isLoadingOlderRef.current) {
        return { messages: [], hasMore: false, nextCursor: null };
      }
      isLoadingOlderRef.current = true;
      setIsLoadingOlder(true);
      try {
        return await fetchPage(beforeCursor);
      } finally {
        isLoadingOlderRef.current = false;
        setIsLoadingOlder(false);
      }
    },
    [user, fetchPage]
  );

  /**
   * Load conversation totals (aggregate tokens and cost)
   */
  const loadConversationTotals = useCallback(async (): Promise<ConversationTotals | null> => {
    if (!user) {
      return null;
    }

    try {
      const response = await apiClient.get<ConversationTotals>('/conversations/me/totals');

      logger.debug(
        'conversation_totals_loaded',
        withContext({
          component: 'useConversation',
          conversationId: response.conversation_id,
          totalCostEur: response.total_cost_eur,
        })
      );

      return response;
    } catch (error: unknown) {
      // 404 is expected for new users without conversation
      if (error && typeof error === 'object' && 'response' in error) {
        const axiosError = error as { response?: { status?: number } };
        if (axiosError.response?.status === 404) {
          logger.debug(
            'conversation_totals_not_found',
            withContext({
              component: 'useConversation',
              reason: 'no_conversation_yet',
            })
          );
          return null;
        }
      }

      logger.error(
        'conversation_totals_load_failed',
        error as Error,
        withContext({
          component: 'useConversation',
          userId: user.id,
        })
      );
      return null;
    }
  }, [user, withContext]);

  /**
   * Reset conversation (soft delete + purge history)
   * Note: Confirmation dialog should be handled by the calling component
   */
  const resetConversation = useCallback(async () => {
    if (!user) {
      throw new Error('User not authenticated');
    }

    try {
      // Always call API - server handles the case where no conversation exists
      await apiClient.post('/conversations/me/reset');

      logger.info(
        'conversation_reset',
        withContext({
          component: 'useConversation',
          conversationId: conversation?.id ?? 'none',
          previousMessageCount: conversation?.message_count ?? 0,
        })
      );

      // Clear local state
      setConversation(null);
    } catch (error) {
      logger.error(
        'conversation_reset_failed',
        error as Error,
        withContext({
          component: 'useConversation',
          conversationId: conversation?.id ?? 'unknown',
        })
      );
      throw error; // Re-throw for parent component to handle
    }
  }, [user, conversation, withContext]);

  /**
   * Load conversation metadata on mount
   */
  useEffect(() => {
    if (user) {
      loadConversation();
    }
  }, [user, loadConversation]);

  return {
    conversation,
    isLoading,
    isLoadingOlder,
    loadConversationPage,
    loadOlderMessages,
    loadConversationTotals,
    resetConversation,
  };
};

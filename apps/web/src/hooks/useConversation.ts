import { useState, useCallback, useEffect } from 'react';
import { apiClient } from '@/lib/api-client';
import { Message } from '@/types/chat';
import { useAuth } from '@/hooks/useAuth';
import { logger } from '@/lib/logger';
import { useLoggingContext } from '@/lib/logging-context';

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
}

export interface ConversationTotals {
  conversation_id: string;
  total_tokens_in: number;
  total_tokens_out: number;
  total_tokens_cache: number;
  total_cost_eur: number;
  total_google_api_requests: number;
}

export interface UseConversationReturn {
  conversation: Conversation | null;
  isLoading: boolean;
  loadConversationHistory: () => Promise<Message[]>;
  loadConversationTotals: () => Promise<ConversationTotals | null>;
  resetConversation: () => Promise<void>;
}

export const useConversation = (): UseConversationReturn => {
  const { user } = useAuth();
  const { withContext } = useLoggingContext();
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [isLoading, setIsLoading] = useState(false);

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
   * Load conversation history (messages)
   * Converts API format to UI Message format
   */
  const loadConversationHistory = useCallback(async (): Promise<Message[]> => {
    if (!user) {
      return [];
    }

    setIsLoading(true);

    try {
      // Try to load messages
      const response = await apiClient.get<{
        messages: ConversationMessage[];
        conversation_id: string;
        total_count: number;
      }>('/conversations/me/messages', {
        params: { limit: 50 },
      });

      // Convert API messages to UI Message format
      const messages: Message[] = response.messages.reverse().map(msg => ({
        id: msg.id,
        content: msg.content,
        role: msg.role,
        timestamp: new Date(msg.created_at),
        // Assistant messages don't have avatar
        // User messages use profile picture if available
        avatar: msg.role === 'user' ? user.picture_url || undefined : undefined,
        // Token usage and cost from backend (snake_case -> camelCase)
        tokensIn: msg.tokens_in ?? undefined,
        tokensOut: msg.tokens_out ?? undefined,
        tokensCache: msg.tokens_cache ?? undefined,
        costEur: msg.cost_eur ?? undefined,
        googleApiRequests: msg.google_api_requests ?? undefined,
        // Message metadata (HITL responses, run_id, etc.) - API uses alias "message_metadata"
        metadata: msg.message_metadata ?? undefined,
      }));

      logger.info(
        'conversation_history_loaded',
        withContext({
          component: 'useConversation',
          messageCount: messages.length,
          conversationId: response.conversation_id,
        })
      );

      return messages;
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
          return [];
        }
      }

      logger.error(
        'conversation_history_load_failed',
        error as Error,
        withContext({
          component: 'useConversation',
          userId: user.id,
        })
      );
      return [];
    } finally {
      setIsLoading(false);
    }
  }, [user, withContext]);

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
    loadConversationHistory,
    loadConversationTotals,
    resetConversation,
  };
};

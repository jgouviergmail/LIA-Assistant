/**
 * Chat state reducer with finite state machine logic.
 *
 * Design Principles:
 * - Pure functions (no side effects)
 * - Immutable state updates
 * - Predictable state transitions
 * - Easy to test (pure reducer function)
 *
 * State Machine Transitions:
 *   idle → sending → streaming → idle
 *          ↓         ↓
 *        error ←----
 */

import { ChatState, ChatAction, initialChatState } from '@/types/chat-state';
import { Message } from '@/types/chat';
import { generateUUID } from '@/lib/utils';

/**
 * Pure reducer function for chat state management.
 *
 * @param state - Current chat state
 * @param action - Action to apply
 * @returns New chat state (immutable)
 */
export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    // ========================================================================
    // User Actions
    // ========================================================================

    case 'SEND_MESSAGE':
      return {
        ...state,
        messages: [...state.messages, action.payload.message],
        status: 'sending',
        streaming: {
          ...state.streaming,
          sseStatus: 'connecting',
        },
        // Clear debug metrics to avoid showing stale data from previous request
        currentDebugMetrics: null,
      };

    case 'CLEAR_MESSAGES':
      return {
        ...state,
        messages: [],
        status: 'idle',
        streaming: {
          currentMessageId: null,
          streamBuffer: '',
          sseStatus: 'disconnected',
        },
        totals: {
          totalTokensIn: 0,
          totalTokensOut: 0,
          totalTokensCache: 0,
          totalCostEur: 0,
          totalMessages: 0,
          totalGoogleApiRequests: 0,
        },
        registry: {}, // LARS: Clear registry when clearing messages

        currentDebugMetrics: null, // Debug Panel: Clear current metrics when clearing messages
        debugMetricsHistory: [], // Debug Panel: Clear history when clearing messages
      };

    case 'SET_MESSAGES': {
      // DEFENSIVE: Ensure messages is always an array
      // NOTE: Validation/logging moved to useChat hook (reducer must be pure)
      const newMessages = Array.isArray(action.payload.messages) ? action.payload.messages : [];

      // PROTECTION: Preserve streaming message during SET_MESSAGES
      // This prevents race conditions when external events (e.g., reminder notifications)
      // trigger a history reload while a response is being streamed.
      // The streaming message may not yet be persisted in the database.
      if (state.status === 'streaming' && state.streaming.currentMessageId) {
        const streamingMsg = state.messages.find(m => m.id === state.streaming.currentMessageId);

        // If the streaming message is not in the new messages, preserve it
        if (streamingMsg && !newMessages.some(m => m.id === streamingMsg.id)) {
          return {
            ...state,
            messages: [...newMessages, streamingMsg],
          };
        }
      }

      return {
        ...state,
        messages: newMessages,
      };
    }

    case 'APPEND_MESSAGE': {
      // Append a single message without replacing the entire messages array
      // Used for real-time notifications (reminders, etc.) to avoid disrupting streaming
      const newMessage = action.payload.message;

      // Deduplicate: ignore if message with same ID already exists
      if (state.messages.some(m => m.id === newMessage.id)) {
        return state;
      }

      return {
        ...state,
        messages: [...state.messages, newMessage],
      };
    }

    // ========================================================================
    // API Health
    // ========================================================================

    case 'SET_API_AVAILABLE':
      return {
        ...state,
        apiAvailable: action.payload.available,
      };

    // ========================================================================
    // SSE Lifecycle
    // ========================================================================

    case 'SSE_CONNECTING':
      return {
        ...state,
        status: 'sending',
        streaming: {
          ...state.streaming,
          sseStatus: 'connecting',
        },
      };

    case 'SSE_CONNECTED':
      return {
        ...state,
        streaming: {
          ...state.streaming,
          sseStatus: 'connected',
        },
      };

    case 'SSE_DISCONNECTED':
      return {
        ...state,
        status: 'idle',
        streaming: {
          currentMessageId: null,
          streamBuffer: '',
          sseStatus: 'disconnected',
        },
      };

    case 'SSE_ERROR':
      return {
        ...state,
        status: 'error',
        streaming: {
          ...state.streaming,
          sseStatus: 'error',
        },
        // Add error message to chat
        messages: [
          ...state.messages,
          {
            id: generateUUID(),
            content: `Erreur de connexion: ${action.payload.error}`,
            role: 'assistant',
            timestamp: new Date(),
          },
        ],
      };

    // ========================================================================
    // Streaming Events
    // ========================================================================

    case 'STREAM_START': {
      // Create assistant message immediately with optional initial content
      // This ensures instant visual feedback when streaming starts
      const initialContent = action.payload.initialContent || '';
      const newMessage: Message = {
        id: action.payload.messageId,
        role: 'assistant',
        content: initialContent, // Can be empty or contain placeholder
        timestamp: new Date(),
      };

      // Note: Removed console.log - content length may leak sensitive information about PII

      return {
        ...state,
        status: 'streaming',
        messages: [...state.messages, newMessage],
        streaming: {
          ...state.streaming,
          currentMessageId: action.payload.messageId,
          streamBuffer: initialContent,
        },
      };
    }

    case 'STREAM_TOKEN': {
      const newBuffer = state.streaming.streamBuffer + action.payload.token;
      const messageId = state.streaming.currentMessageId;

      // NOTE: Validation/logging moved to useChat hook (reducer must be pure)
      if (!messageId) {
        // No active stream, ignore token silently
        return state;
      }

      // Find and update existing message
      const existingIndex = state.messages.findIndex(m => m.id === messageId);

      if (existingIndex >= 0) {
        // Update existing message
        const updatedMessages = [...state.messages];
        updatedMessages[existingIndex] = {
          ...updatedMessages[existingIndex],
          content: newBuffer,
        };

        return {
          ...state,
          messages: updatedMessages,
          streaming: {
            ...state.streaming,
            streamBuffer: newBuffer,
          },
        };
      } else {
        // Message should exist (created by STREAM_START)
        // Validation/logging handled by hook
        return state;
      }
    }

    case 'STREAM_REPLACE': {
      // Replace entire content instead of appending (used for replacing placeholder)
      const newContent = action.payload.content;
      const messageId = state.streaming.currentMessageId;

      if (!messageId) {
        return state;
      }

      const existingIndex = state.messages.findIndex(m => m.id === messageId);

      if (existingIndex >= 0) {
        const updatedMessages = [...state.messages];
        updatedMessages[existingIndex] = {
          ...updatedMessages[existingIndex],
          content: newContent, // Replace entirely, not append
        };

        return {
          ...state,
          messages: updatedMessages,
          streaming: {
            ...state.streaming,
            streamBuffer: newContent, // Reset buffer to new content
          },
        };
      }

      return state;
    }

    case 'STREAM_DONE': {
      const { messageId, metadata } = action.payload;

      // Update message with metadata if provided
      let updatedMessages = state.messages;
      if (metadata) {
        const messageIndex = state.messages.findIndex(m => m.id === messageId);

        if (messageIndex >= 0) {
          // Message exists - update it with metadata
          updatedMessages = state.messages.map(m =>
            m.id === messageId
              ? {
                  ...m,
                  tokensIn: metadata.tokens_in,
                  tokensOut: metadata.tokens_out,
                  tokensCache: metadata.tokens_cache,
                  costEur: metadata.cost_eur,
                  googleApiRequests: metadata.google_api_requests,
                  skillName: metadata.skill_name,
                }
              : m
          );
        } else {
          // Message doesn't exist - find last assistant message and update it
          // This can happen when done chunk arrives without prior streaming
          const reversedIndex = [...state.messages]
            .reverse()
            .findIndex(m => m.role === 'assistant');

          if (reversedIndex >= 0) {
            const lastAssistantIndex = state.messages.length - 1 - reversedIndex;
            const lastMsg = state.messages[lastAssistantIndex];

            // ✅ SAFETY: Don't attach tokens to plan messages (ephemeral HITL state)
            // Plan messages are temporary UI state during approval flow
            // Tokens should only attach to final response messages, not plans
            const isPlanMessage =
              lastMsg.content.startsWith("Je vais d'abord") ||
              lastMsg.content.includes('Tu confirmes que je procède') ||
              lastMsg.content.includes('Je valide les accès');

            if (!isPlanMessage) {
              updatedMessages = state.messages.map((m, index) =>
                index === lastAssistantIndex
                  ? {
                      ...m,
                      tokensIn: metadata.tokens_in,
                      tokensOut: metadata.tokens_out,
                      tokensCache: metadata.tokens_cache,
                      costEur: metadata.cost_eur,
                      googleApiRequests: metadata.google_api_requests,
                      skillName: metadata.skill_name,
                    }
                  : m
              );
            }
            // If it's a plan message, skip token attachment (tokens will attach to final response later)
          }
        }
      }

      // Update conversation totals
      const updatedTotals = metadata
        ? {
            totalTokensIn: state.totals.totalTokensIn + (metadata.tokens_in || 0),
            totalTokensOut: state.totals.totalTokensOut + (metadata.tokens_out || 0),
            totalTokensCache: state.totals.totalTokensCache + (metadata.tokens_cache || 0),
            totalCostEur: state.totals.totalCostEur + (metadata.cost_eur || 0),
            totalMessages: state.totals.totalMessages + (metadata.message_count || 0),
            totalGoogleApiRequests:
              state.totals.totalGoogleApiRequests + (metadata.google_api_requests || 0),
          }
        : state.totals;

      return {
        ...state,
        status: 'idle',
        messages: updatedMessages,
        totals: updatedTotals,
        streaming: {
          currentMessageId: null,
          streamBuffer: '',
          sseStatus: 'disconnected',
        },
      };
    }

    case 'STREAM_ERROR':
      return {
        ...state,
        status: 'error',
        streaming: {
          ...state.streaming,
          sseStatus: 'error',
        },
        // Add error message to chat
        messages: [
          ...state.messages,
          {
            id: generateUUID(),
            content: `Erreur: ${action.payload.error}`,
            role: 'assistant',
            timestamp: new Date(),
          },
        ],
      };

    // ========================================================================
    // Router Metadata (informational only)
    // ========================================================================

    case 'ROUTER_DECISION':
      // Router decision is logged but doesn't change state
      // We could add a `lastRouterDecision` field to state if needed
      return state;

    // ========================================================================
    // HITL: Approval Message Management
    // ========================================================================

    case 'ADD_APPROVAL_MESSAGE':
      // Removed console.log - approval message debugging
      return {
        ...state,
        messages: [...state.messages, action.payload.message],
      };

    case 'REMOVE_APPROVAL_MESSAGE':
      return {
        ...state,
        messages: state.messages.filter(m => m.id !== action.payload.messageId),
      };

    // ========================================================================
    // LARS: Registry Management (side-channel data for rich rendering)
    // ========================================================================

    case 'REGISTRY_UPDATE': {
      // Merge new items into registry (last write wins for same ID)
      // Items are received via SSE registry_update events BEFORE tokens
      const newItems = action.payload.items;

      return {
        ...state,
        registry: {
          ...state.registry,
          ...newItems,
        },
      };
    }

    case 'REGISTRY_CLEAR':
      // Clear registry (typically on conversation clear or explicit reset)
      return {
        ...state,
        registry: {},
      };

    // ========================================================================
    // Debug Panel: Scoring Metrics (DEBUG=true only)
    // ========================================================================

    case 'DEBUG_METRICS_SET':
      // Store debug metrics for current request (real-time display during streaming)
      // Also add to history for cumulative display (prepend = most recent first)
      return {
        ...state,
        currentDebugMetrics: action.payload.metrics,
      };

    case 'DEBUG_METRICS_ADD_TO_HISTORY': {
      // Add completed request metrics to cumulative history
      // Keep max 20 entries to prevent memory issues
      const MAX_HISTORY_ENTRIES = 20;
      const newHistory = [action.payload.entry, ...state.debugMetricsHistory].slice(
        0,
        MAX_HISTORY_ENTRIES
      );
      return {
        ...state,
        debugMetricsHistory: newHistory,
      };
    }

    case 'DEBUG_METRICS_UPDATE': {
      // Merge supplementary metrics (e.g., journal extraction) into current + latest history
      const update = action.payload.metrics;
      const updatedCurrent = state.currentDebugMetrics
        ? { ...state.currentDebugMetrics, ...update }
        : null;
      const updatedHistory = state.debugMetricsHistory.length > 0
        ? [
            { ...state.debugMetricsHistory[0], metrics: { ...state.debugMetricsHistory[0].metrics, ...update } },
            ...state.debugMetricsHistory.slice(1),
          ]
        : [];
      return {
        ...state,
        currentDebugMetrics: updatedCurrent,
        debugMetricsHistory: updatedHistory,
      };
    }

    case 'DEBUG_METRICS_CLEAR':
      // Clear all debug metrics (current + history)
      return {
        ...state,
        currentDebugMetrics: null,
        debugMetricsHistory: [],
      };

    // ========================================================================
    // Default
    // ========================================================================

    default:
      // TypeScript exhaustiveness check
      // @ts-expect-error - Exhaustiveness check pattern

      const _exhaustiveCheck: never = action;
      return state;
  }
}

/**
 * Helper to create initial state (useful for testing).
 */
export function createInitialState(): ChatState {
  return initialChatState;
}

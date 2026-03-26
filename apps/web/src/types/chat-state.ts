/**
 * Chat state machine types and constants for useReducer pattern.
 *
 * State Machine:
 *   idle → sending → streaming → idle
 *          ↓         ↓
 *        error ←----
 *
 * Design Principles:
 * - Single source of truth for chat state
 * - Predictable state transitions (finite state machine)
 * - Type-safe actions with discriminated unions
 * - Immutable state updates
 */

import { Message, RegistryItem, DebugMetrics } from './chat';

// ============================================================================
// SSE Constants
// ============================================================================

export const SSE_CHUNK_TYPES = {
  TOKEN: 'token',
  ROUTER_DECISION: 'router_decision',
  ERROR: 'error',
  DONE: 'done',
  TOOL_APPROVAL_REQUEST: 'tool_approval_request',
} as const;

export const SSE_STATUS = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  ERROR: 'error',
} as const;

// ============================================================================
// Chat State Machine
// ============================================================================

export type ChatStatus =
  | 'idle' // No active conversation
  | 'sending' // User message sent, waiting for response
  | 'streaming' // Assistant response streaming
  | 'error'; // Error state

export interface ConversationTotals {
  totalTokensIn: number;
  totalTokensOut: number;
  totalTokensCache: number;
  totalCostEur: number;
  totalMessages: number;
  totalGoogleApiRequests: number;
}

export interface StreamingMetadata {
  currentMessageId: string | null;
  streamBuffer: string;
  sseStatus: 'connecting' | 'connected' | 'disconnected' | 'error';
}

/**
 * Debug metrics entry for cumulative history display.
 *
 * Each entry represents a single request's debug metrics,
 * allowing the debug panel to show a collapsible history of all requests.
 */
export interface DebugMetricsEntry {
  /** Unique ID for React key */
  id: string;
  /** Timestamp when the request was made */
  timestamp: Date;
  /** User's original query (for display in collapsed header) */
  query: string;
  /** Full debug metrics for this request */
  metrics: DebugMetrics;
}

export interface ChatState {
  // Messages
  messages: Message[];

  // State machine status
  status: ChatStatus;

  // Streaming state
  streaming: StreamingMetadata;

  // Conversation metrics
  totals: ConversationTotals;

  // API availability
  apiAvailable: boolean;

  // History loading (for future use)
  isLoadingHistory: boolean;

  // LARS: Registry for rich frontend rendering
  // Items are received via SSE registry_update events BEFORE tokens
  // Frontend resolves DSL tags (<View id="..."/>, <Ref id="..."/>) to these items
  registry: Record<string, RegistryItem>;

  // Debug Panel: Current request metrics (for real-time display during streaming)
  // Set when debug_metrics chunk arrives, cleared on new request
  currentDebugMetrics: DebugMetrics | null;

  // Debug Panel: Cumulative history of all request metrics (v3.2)
  // Allows collapsible display of past requests for comparison and debugging
  // Most recent entry is displayed first and expanded by default
  debugMetricsHistory: DebugMetricsEntry[];
}

// ============================================================================
// Action Types (Discriminated Union)
// ============================================================================

export type ChatAction =
  // User actions
  | { type: 'SEND_MESSAGE'; payload: { message: Message } }
  | { type: 'CLEAR_MESSAGES' }
  | { type: 'SET_MESSAGES'; payload: { messages: Message[] } }
  | { type: 'APPEND_MESSAGE'; payload: { message: Message } }

  // API health
  | { type: 'SET_API_AVAILABLE'; payload: { available: boolean } }

  // SSE lifecycle
  | { type: 'SSE_CONNECTING' }
  | { type: 'SSE_CONNECTED' }
  | { type: 'SSE_DISCONNECTED' }
  | { type: 'SSE_ERROR'; payload: { error: string } }

  // Streaming events
  | { type: 'STREAM_START'; payload: { messageId: string; initialContent?: string } }
  | { type: 'STREAM_TOKEN'; payload: { token: string } }
  | { type: 'STREAM_REPLACE'; payload: { content: string } }
  | {
      type: 'STREAM_DONE';
      payload: {
        messageId: string;
        metadata?: {
          tokens_in?: number;
          tokens_out?: number;
          tokens_cache?: number;
          cost_eur?: number;
          message_count?: number;
          google_api_requests?: number;
          skill_name?: string;
          generated_images?: { url: string; alt: string }[];
        };
      };
    }
  | { type: 'STREAM_ERROR'; payload: { error: string } }

  // Router metadata (informational)
  | {
      type: 'ROUTER_DECISION';
      payload: {
        intention: string;
        confidence: number;
        context_label: string;
        next_node: string;
        reasoning?: string | null;
      };
    }

  // HITL: Add approval message to chat
  | { type: 'ADD_APPROVAL_MESSAGE'; payload: { message: Message } }

  // HITL: Remove approval message after processing
  | { type: 'REMOVE_APPROVAL_MESSAGE'; payload: { messageId: string } }

  // LARS: Registry update (side-channel data for rich rendering)
  | { type: 'REGISTRY_UPDATE'; payload: { items: Record<string, RegistryItem> } }

  // LARS: Clear registry (on conversation clear)
  | { type: 'REGISTRY_CLEAR' }

  // Debug Panel: Set debug metrics for current request (real-time during streaming)
  | { type: 'DEBUG_METRICS_SET'; payload: { metrics: DebugMetrics } }

  // Debug Panel: Add metrics to cumulative history (on request completion)
  | { type: 'DEBUG_METRICS_ADD_TO_HISTORY'; payload: { entry: DebugMetricsEntry } }

  // Debug Panel: Merge supplementary metrics into current + latest history entry
  | { type: 'DEBUG_METRICS_UPDATE'; payload: { metrics: Partial<DebugMetrics> } }

  // Debug Panel: Clear all debug metrics (current + history)
  | { type: 'DEBUG_METRICS_CLEAR' };

// ============================================================================
// Initial State
// ============================================================================

export const initialChatState: ChatState = {
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
  apiAvailable: false,
  isLoadingHistory: false,
  registry: {}, // LARS: Empty registry at start
  currentDebugMetrics: null, // Debug Panel: No current metrics at start
  debugMetricsHistory: [], // Debug Panel: Empty history at start
};

// ============================================================================
// Type Guards (for safer state access)
// ============================================================================

export function isStreaming(state: ChatState): boolean {
  return state.status === 'streaming';
}

export function isIdle(state: ChatState): boolean {
  return state.status === 'idle';
}

export function hasError(state: ChatState): boolean {
  return state.status === 'error' || state.streaming.sseStatus === 'error';
}

export function canSendMessage(state: ChatState): boolean {
  return state.status === 'idle' && state.apiAvailable;
}

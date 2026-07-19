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

import { Message, RegistryItem, DebugMetrics, BrowserScreenshotData } from './chat';
import { HitlCardState, NormalizedHitlPayload, initialHitlCardState } from './hitl';
import type { ExecutionTrace } from './execution-trace';

// ============================================================================
// Chat State Machine
// ============================================================================

export type ChatStatus =
  | 'idle' // No active conversation
  | 'sending' // User message sent, waiting for response
  | 'streaming' // Assistant response streaming
  | 'compacting' // Conversation history summarization in progress (compaction v2)
  | 'error'; // Error state

/**
 * State of a conversation history compaction surfaced by backend SSE events.
 *
 * - phase = 'in_progress': compaction_start received; UI shows the progress banner
 *   and locks the chat input.
 * - phase = 'done': compaction_done received with a real LLM summary.
 * - phase = 'truncated': compaction_done received with strategy='truncation'
 *   (the fallback path); UI shows the explicit truncation notice.
 */
export interface CompactionState {
  phase: 'in_progress' | 'done' | 'truncated';
  estimatedDurationSeconds?: number;
  startedAt?: number; // Date.now() at compaction_start arrival
  tokensSaved?: number;
  durationMs?: number;
  strategy?: string;
}

/**
 * Snapshot of the conversation's current token footprint relative to the
 * compaction threshold. Updated on every `done` SSE event when the backend
 * exposes `context_tokens` + `context_threshold` in the metadata.
 *
 * Drives the small progress pill rendered in the chat header bar.
 */
export interface ContextUsage {
  tokens: number;
  threshold: number;
  /** `tokens / threshold` clamped to [0, 1.5] so a slightly post-threshold
   * compaction window still displays a meaningful value. */
  ratio: number;
}

export interface ConversationTotals {
  totalTokensIn: number;
  totalTokensOut: number;
  totalTokensCache: number;
  totalCostEur: number;
  totalMessages: number;
  totalGoogleApiRequests: number;
}

/**
 * Content phase of the active stream: 'progress' while the message shows the
 * accumulated execution steps (*📋 …* lines), 'answer' once real tokens
 * replace them. Drives step styling and the streaming caret in ChatMessage.
 */
export type StreamPhase = 'progress' | 'answer';

export interface StreamingMetadata {
  currentMessageId: string | null;
  streamBuffer: string;
  sseStatus: 'connecting' | 'connected' | 'disconnected' | 'error';
  phase: StreamPhase;
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

  // Browser Screenshots: Current overlay data (progressive screenshots during browsing)
  browserScreenshot: BrowserScreenshotData | null;

  // Compaction v2 (2026-05): state of an in-flight or just-finished history
  // compaction. Drives the chat-input lock (`status === 'compacting'` flows
  // through useChat's `isTyping` derived state) and the sonner toast emitted
  // from `handleCompactionStep`. `null` when no compaction has run yet or
  // after the next user turn cleared it.
  compaction: CompactionState | null;

  // Context-usage pill (2026-05): current conversation token footprint vs
  // compaction threshold. Set on every `done` SSE event when the backend
  // exposes the figures. `null` until the first turn completes.
  contextUsage: ContextUsage | null;

  // HITL approval card (Lot 1 P1-V1): lifecycle of the one-click approval
  // card built from `hitl_interrupt_metadata` chunks (or rehydrated via
  // GET /agents/hitl/pending after a reload). The text/voice reply channel
  // stays fully functional in parallel — see the SEND_MESSAGE interaction.
  hitl: HitlCardState;

  // Actionable connector error notices (Lot 3 P3, ADR-134): "reconnect" /
  // "rate limit" banners built from `tool_error` execution steps emitted by
  // the backend when a connector auth failure breaks a tool. Deduplicated by
  // (connectorType, action) here — the backend emits once per failed step.
  connectorNotices: ConnectorNotice[];
}

/** One actionable connector failure surfaced under the chat input. */
export interface ConnectorNotice {
  /** Backend connector type value, e.g. "google_gmail". */
  connectorType: string;
  /** What the user can do about it. */
  action: 'reconnect' | 'rate_limit';
  /** The failing tool (context for logs; not necessarily displayed). */
  toolName: string;
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
  | {
      type: 'STREAM_START';
      payload: { messageId: string; initialContent?: string; phase?: StreamPhase };
    }
  | { type: 'STREAM_TOKEN'; payload: { token: string } }
  | { type: 'STREAM_REPLACE'; payload: { content: string; phase?: StreamPhase } }
  | {
      type: 'STREAM_DONE';
      payload: {
        messageId: string;
        metadata?: {
          // ADR-117 Lot 3: synthesized done of a user-cancelled run — the
          // partial bubble is kept and badged "interrupted" (same flag as
          // archived history rows). Mirror of DoneMetadata.cancelled.
          cancelled?: boolean;
          tokens_in?: number;
          tokens_out?: number;
          tokens_cache?: number;
          cost_eur?: number;
          message_count?: number;
          google_api_requests?: number;
          // Per-message TTS attribution carried in the SSE done chunk
          // — paid providers only. Edge stays absent. Mirror of STT.
          tts_provider?: string;
          tts_model?: string;
          tts_characters?: number;
          tts_cost_eur?: number;
          skill_name?: string;
          // Context-usage pill (2026-05): current conversation token footprint
          // and the dynamic compaction threshold. Used to render a small
          // progress pill in the chat header bar.
          context_tokens?: number;
          context_threshold?: number;
          generated_images?: { url: string; alt: string }[];
          browser_screenshot?: { url: string; alt: string };
          psyche_state?: {
            mood_label: string;
            mood_color: string;
            mood_pleasure: number;
            mood_arousal: number;
            mood_dominance: number;
            active_emotion: string | null;
            emotion_intensity: number;
            relationship_stage: string;
          };
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
  | { type: 'DEBUG_METRICS_CLEAR' }

  // Browser Screenshots: Progressive screenshot overlay
  | { type: 'BROWSER_SCREENSHOT'; payload: BrowserScreenshotData }
  | { type: 'BROWSER_SCREENSHOT_CLEAR' }

  // Compaction v2 (2026-05): SSE compaction_start/compaction_done events
  // emitted by the backend's compaction_node via the LangGraph "custom"
  // stream mode. Drive the chat-input lock and progress banner.
  | {
      type: 'STREAM_COMPACTION_START';
      payload: { estimatedDurationSeconds?: number; strategy?: string };
    }
  | {
      type: 'STREAM_COMPACTION_DONE';
      payload: { tokensSaved?: number; durationMs?: number; strategy?: string };
    }

  // Context-usage pill hydration (2026-05): set on page load from the
  // /conversations/me/totals payload so the pill is visible immediately,
  // not only after the first `done` event.
  | {
      type: 'CONTEXT_USAGE_HYDRATE';
      payload: { tokens: number; threshold: number };
    }

  // Execution trace (Lot 2 P2-V1): attach the captured backstage record
  // (steps + reasoning + duration) to a completed assistant message so it
  // survives the response instead of being wiped at the progress→answer flip.
  | {
      type: 'TRACE_ATTACH';
      payload: { messageId: string; trace: ExecutionTrace };
    }

  // Connector error notices (Lot 3 P3): ADD dedupes by (connectorType,
  // action); DISMISS removes one banner; notices are cleared on the next
  // SEND_MESSAGE (a new turn gets a fresh verdict).
  | { type: 'CONNECTOR_NOTICE_ADD'; payload: { notice: ConnectorNotice } }
  | {
      type: 'CONNECTOR_NOTICE_DISMISS';
      payload: { connectorType: string; action: ConnectorNotice['action'] };
    }

  // HITL approval card (Lot 1 P1-V1). Last-wins: a new interrupt replaces
  // any previous card state.
  | { type: 'HITL_AWAITING'; payload: { payload: NormalizedHitlPayload } }
  // Button pressed — buttons lock while the decision request is in flight.
  | { type: 'HITL_SUBMITTING'; payload: { action: 'confirm' | 'cancel' } }
  // Typed error from the backend: the decision no longer matches the pending
  // interrupt (expired / already answered / superseded).
  | { type: 'HITL_EXPIRED' }
  // Reset (conversation cleared).
  | { type: 'HITL_CLEAR' };

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
    phase: 'answer',
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
  browserScreenshot: null, // Browser Screenshots: No overlay at start
  compaction: null, // Compaction v2: no compaction in flight or recorded
  contextUsage: null, // Context pill: no measurement yet (first turn not done)
  hitl: initialHitlCardState, // HITL card: no interrupt pending at start
  connectorNotices: [], // Lot 3 P3: no connector failure surfaced at start
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

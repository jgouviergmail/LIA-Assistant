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
 *
 * Structure (audit F011): every action is a pure handler in the
 * ``ACTION_HANDLERS`` decision table, so ``chatReducer`` stays a one-line
 * dispatch and each transition is independently testable. The mapped-type
 * table also enforces exhaustiveness at compile time (a new ChatAction member
 * without a handler is a type error), which replaced the former switch's
 * suppressed never-check in the default branch. Behavior is pinned by the 97
 * tests under __tests__/.
 */

import { ChatState, ChatAction, initialChatState } from '@/types/chat-state';
import { initialHitlCardState } from '@/types/hitl';
import { MAX_TRACE_STEPS } from '@/types/execution-trace';
import { Message } from '@/types/chat';
import { generateUUID } from '@/lib/utils';
import { DEBUG_METRICS_HISTORY_KEY } from '@/lib/constants';

/** Non-optional shape of the STREAM_DONE metadata payload. */
type StreamDoneMetadata = NonNullable<
  Extract<ChatAction, { type: 'STREAM_DONE' }>['payload']['metadata']
>;

/** A pure handler for one action type, receiving the narrowed action. */
type ChatActionHandler<K extends ChatAction['type']> = (
  state: ChatState,
  action: Extract<ChatAction, { type: K }>
) => ChatState;

/** Exhaustive decision table: one handler per ChatAction member. */
type ChatActionHandlers = { [K in ChatAction['type']]: ChatActionHandler<K> };

// ============================================================================
// STREAM_DONE helpers (extracted so the handler stays flat)
// ============================================================================

/** Attach the SSE ``done`` metadata (tokens, TTS attribution, psyche snapshot,
 * cancellation badge) to a single message. Shared by both STREAM_DONE branches
 * (matched-id and last-assistant fallback) so the patch never drifts. */
function applyDoneMetadata(m: Message, metadata: StreamDoneMetadata): Message {
  return {
    ...m,
    tokensIn: metadata.tokens_in,
    tokensOut: metadata.tokens_out,
    tokensCache: metadata.tokens_cache,
    costEur: metadata.cost_eur,
    googleApiRequests: metadata.google_api_requests,
    // Per-message TTS attribution (live badge — paid providers only)
    ttsProvider: metadata.tts_provider ?? null,
    ttsModel: metadata.tts_model ?? null,
    ttsCharacters: metadata.tts_characters ?? null,
    ttsCostEur: metadata.tts_cost_eur ?? null,
    skillName: metadata.skill_name,
    // No assertion: both sides now name the same `GeneratedImage` /
    // `GeneratedDocument` shapes, so a future field lands on the action
    // payload and the message together.
    generatedImages: metadata.generated_images,
    generatedDocuments: metadata.generated_documents,
    browserScreenshot: metadata.browser_screenshot as { url: string; alt: string } | undefined,
    // Store psyche state snapshot for avatar display.
    // ADR-117 Lot 3: a cancelled run's synthesized done flags the partial
    // bubble with the SAME `interrupted` field as archived history rows — one
    // badge for live and reload.
    metadata: {
      ...m.metadata,
      psyche_state: metadata.psyche_state,
      ...(metadata.cancelled ? { interrupted: true, interrupt_reason: 'cancelled' } : {}),
      // QW-5 (ADR-138): DB id of the archived row — the feedback buttons only
      // render when a message can be targeted server-side.
      ...(metadata.archived_message_id ? { message_db_id: metadata.archived_message_id } : {}),
      // UXR Lot 4 (A2): follow-up chips — same field name as the archived
      // message_metadata so live and reloaded rows read identically.
      ...(metadata.followup_suggestions?.length
        ? { followup_suggestions: metadata.followup_suggestions }
        : {}),
      // Lot 1-A3: provenance line of the chips (same live/reload symmetry).
      ...(metadata.initiative_motivation
        ? { initiative_motivation: metadata.initiative_motivation }
        : {}),
    },
  };
}

/** Apply the done metadata to the target message: the one matching
 * ``messageId``, or — when a ``done`` lands without prior streaming — the last
 * assistant bubble, UNLESS it is an ephemeral HITL prompt (id prefix
 * ``hitl_``; language-agnostic, unlike the previous French-content matching). */
function applyDoneToMessages(
  messages: Message[],
  messageId: string,
  metadata: StreamDoneMetadata
): Message[] {
  const existingIndex = messages.findIndex(m => m.id === messageId);
  if (existingIndex >= 0) {
    return messages.map(m => (m.id === messageId ? applyDoneMetadata(m, metadata) : m));
  }

  // Message doesn't exist - find last assistant message and update it.
  const reversedIndex = [...messages].reverse().findIndex(m => m.role === 'assistant');
  if (reversedIndex < 0) return messages;

  const lastAssistantIndex = messages.length - 1 - reversedIndex;
  // SAFETY: don't attach tokens to HITL prompt messages (ephemeral approval
  // state) — tokens should only attach to final response messages.
  if (messages[lastAssistantIndex].id.startsWith('hitl_')) return messages;

  return messages.map((m, index) =>
    index === lastAssistantIndex ? applyDoneMetadata(m, metadata) : m
  );
}

/** Accumulate the conversation totals with this turn's usage. */
function accumulateTotals(totals: ChatState['totals'], metadata: StreamDoneMetadata) {
  return {
    totalTokensIn: totals.totalTokensIn + (metadata.tokens_in || 0),
    totalTokensOut: totals.totalTokensOut + (metadata.tokens_out || 0),
    totalTokensCache: totals.totalTokensCache + (metadata.tokens_cache || 0),
    totalCostEur: totals.totalCostEur + (metadata.cost_eur || 0),
    totalMessages: totals.totalMessages + (metadata.message_count || 0),
    totalGoogleApiRequests: totals.totalGoogleApiRequests + (metadata.google_api_requests || 0),
  };
}

/** Context-usage pill (2026-05): refresh from the latest done tokens/threshold,
 * keeping the previous value when the backend omitted them (best-effort). */
function nextContextUsage(
  state: ChatState,
  metadata: StreamDoneMetadata | undefined
): ChatState['contextUsage'] {
  if (
    metadata?.context_tokens === undefined ||
    metadata?.context_threshold === undefined ||
    metadata.context_threshold <= 0
  ) {
    return state.contextUsage;
  }
  return {
    tokens: metadata.context_tokens,
    threshold: metadata.context_threshold,
    ratio: Math.min(1.5, metadata.context_tokens / metadata.context_threshold),
  };
}

// ============================================================================
// Action handlers (one pure transition per action)
// ============================================================================

/**
 * HITL card interaction with an outgoing user message (Lot 1 P1-V1).
 *
 * A typed reply while the card is 'awaiting' resolves it via_text — the
 * conversational channel always wins, the card must never block it. The
 * button flow dispatches HITL_SUBMITTING BEFORE its own send, so a
 * 'submitting' card passes through unchanged. An 'expired' card is cleared:
 * the user moved on, the stale note has served its purpose.
 */
function hitlAfterSend(hitl: ChatState['hitl']): ChatState['hitl'] {
  if (hitl.status === 'awaiting') {
    return { ...hitl, status: 'resolved', resolution: 'via_text' };
  }
  if (hitl.status === 'expired') {
    return initialHitlCardState;
  }
  return hitl;
}

/**
 * Build the bubble that reports a failed turn (W3).
 *
 * A failure used to end as an anonymous assistant bubble: the user had to find
 * their question and retype it. The bubble is now marked as an error AND pins
 * the prompt that produced it, so the retry replays exactly what was asked —
 * not whatever happens to be the latest user text when the button is pressed
 * (a proactive notification can land in between).
 *
 * `retryPrompt` is omitted when nothing meaningful can be replayed: a failure
 * with no preceding question (a proactive turn), or an empty one.
 */
function errorBubble(messages: Message[], error: string): Message {
  const lastUserText = [...messages]
    .reverse()
    .find(m => m.role === 'user')
    ?.content?.trim();
  return {
    id: generateUUID(),
    content: error,
    role: 'assistant',
    timestamp: new Date(),
    metadata: {
      type: 'error',
      ...(lastUserText ? { retryPrompt: lastUserText } : {}),
    },
  };
}

const ACTION_HANDLERS: ChatActionHandlers = {
  // ------------------------------------------------------------------ User
  SEND_MESSAGE: (state, action) => ({
    ...state,
    messages: [...state.messages, action.payload.message],
    status: 'sending',
    streaming: {
      ...state.streaming,
      sseStatus: 'connecting',
    },
    // Clear debug metrics to avoid showing stale data from previous request
    currentDebugMetrics: null,
    // Clear browser screenshot overlay from previous request
    browserScreenshot: null,
    // Clear any previous compaction banner — a new turn starts fresh.
    compaction: null,
    // HITL card: a typed reply resolves an awaiting card via_text.
    hitl: hitlAfterSend(state.hitl),
    // Connector notices: a new turn gets a fresh verdict (Lot 3 P3).
    connectorNotices: [],
  }),

  CLEAR_MESSAGES: state => ({
    ...state,
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
    registry: {}, // LARS: Clear registry when clearing messages

    currentDebugMetrics: null, // Debug Panel: Clear current metrics when clearing messages
    debugMetricsHistory: [], // Debug Panel: Clear history when clearing messages
    browserScreenshot: null, // Browser Screenshots: Clear overlay when clearing messages
    compaction: null, // Compaction v2: clear banner when clearing messages
    contextUsage: null, // Context pill: stale once messages are wiped
    hitl: initialHitlCardState, // HITL card: a wiped conversation has no pending interrupt
  }),

  SET_MESSAGES: (state, action) => {
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
  },

  APPEND_MESSAGE: (state, action) => {
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
  },

  // ------------------------------------------------------------------ API Health
  SET_API_AVAILABLE: (state, action) => ({
    ...state,
    apiAvailable: action.payload.available,
  }),

  // ------------------------------------------------------------------ SSE Lifecycle
  SSE_CONNECTING: state => ({
    ...state,
    status: 'sending',
    streaming: {
      ...state.streaming,
      sseStatus: 'connecting',
    },
  }),

  SSE_CONNECTED: state => ({
    ...state,
    streaming: {
      ...state.streaming,
      sseStatus: 'connected',
    },
  }),

  SSE_DISCONNECTED: state => ({
    ...state,
    status: 'idle',
    streaming: {
      currentMessageId: null,
      streamBuffer: '',
      sseStatus: 'disconnected',
      phase: 'answer',
    },
  }),

  SSE_ERROR: (state, action) => ({
    ...state,
    status: 'error',
    streaming: {
      ...state.streaming,
      sseStatus: 'error',
    },
    // Add error message to chat. The payload arrives ALREADY localized
    // (useChat resolves the ChatStreamError i18nKey / generic key through
    // t()) — the pure reducer has no i18n access and must not prepend
    // hardcoded text in any language.
    messages: [...state.messages, errorBubble(state.messages, action.payload.error)],
  }),

  // ------------------------------------------------------------------ Streaming Events
  STREAM_START: (state, action) => {
    // Create assistant message immediately with optional initial content
    // This ensures instant visual feedback when streaming starts
    const initialContent = action.payload.initialContent || '';

    // Idempotent: if message already exists (e.g., created by router progress),
    // just ensure currentMessageId is set so STREAM_REPLACE has a target.
    // This prevents duplicate messages when handleContentReplacement re-dispatches
    // STREAM_START after a progress message was already created.
    const existingIndex = state.messages.findIndex(m => m.id === action.payload.messageId);
    if (existingIndex >= 0) {
      return {
        ...state,
        status: 'streaming',
        streaming: {
          ...state.streaming,
          currentMessageId: action.payload.messageId,
          streamBuffer: state.messages[existingIndex].content,
          phase: action.payload.phase ?? state.streaming.phase,
        },
      };
    }

    const newMessage: Message = {
      id: action.payload.messageId,
      role: 'assistant',
      content: initialContent,
      timestamp: new Date(),
    };

    return {
      ...state,
      status: 'streaming',
      messages: [...state.messages, newMessage],
      streaming: {
        ...state.streaming,
        currentMessageId: action.payload.messageId,
        streamBuffer: initialContent,
        phase: action.payload.phase ?? state.streaming.phase,
      },
    };
  },

  STREAM_TOKEN: (state, action) => {
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
  },

  STREAM_REPLACE: (state, action) => {
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
          phase: action.payload.phase ?? state.streaming.phase,
        },
      };
    }

    return state;
  },

  STREAM_DONE: (state, action) => {
    const { messageId, metadata } = action.payload;

    // Update message with metadata if provided
    const updatedMessages = metadata
      ? applyDoneToMessages(state.messages, messageId, metadata)
      : state.messages;

    // Update conversation totals
    const updatedTotals = metadata ? accumulateTotals(state.totals, metadata) : state.totals;

    // HITL card: a submitted decision resolves when its stream completes.
    // An 'awaiting' card is never touched here — the interrupt stream itself
    // ends WITHOUT a done chunk (runtime-proven protocol fact). A submitting
    // (button flow) or resolved (via_text flow) card is CLEARED: the reply
    // bubble is the outcome feedback, a lingering card is noise (user
    // feedback 2026-07-19). An expired card stays — its turn produced no
    // outcome, the note explains why (cleared on the next send).
    const hitlAfterDone: ChatState['hitl'] =
      state.hitl.status === 'submitting' || state.hitl.status === 'resolved'
        ? initialHitlCardState
        : state.hitl;

    return {
      ...state,
      status: 'idle',
      messages: updatedMessages,
      totals: updatedTotals,
      streaming: {
        currentMessageId: null,
        streamBuffer: '',
        sseStatus: 'disconnected',
        phase: 'answer',
      },
      browserScreenshot: null, // Clear overlay when stream completes
      contextUsage: nextContextUsage(state, metadata),
      hitl: hitlAfterDone,
    };
  },

  STREAM_ERROR: (state, action) => ({
    ...state,
    status: 'error',
    streaming: {
      ...state.streaming,
      sseStatus: 'error',
    },
    // Add error message to chat (already localized by backend)
    messages: [...state.messages, errorBubble(state.messages, action.payload.error)],
    // HITL card: a transport failure while submitting re-arms the buttons
    // (retryable). The typed hitl_decision_stale error dispatches
    // HITL_EXPIRED separately — this branch only covers generic failures.
    hitl:
      state.hitl.status === 'submitting'
        ? { ...state.hitl, status: 'awaiting', submittedAction: null }
        : state.hitl,
  }),

  // ------------------------------------------------------------------ Router Metadata
  // Router decision is logged but doesn't change state.
  ROUTER_DECISION: state => state,

  // ------------------------------------------------------------ Execution trace
  // Attach the captured backstage record to a completed assistant message
  // (Lot 2 P2-V1). Targets by id; no-op on unknown id; caps retained steps.
  TRACE_ATTACH: (state, action) => {
    const { messageId, trace } = action.payload;
    const index = state.messages.findIndex(m => m.id === messageId);
    if (index < 0) return state;

    const cappedSteps =
      trace.steps.length > MAX_TRACE_STEPS ? trace.steps.slice(-MAX_TRACE_STEPS) : trace.steps;

    const updatedMessages = [...state.messages];
    updatedMessages[index] = {
      ...updatedMessages[index],
      executionTrace: { ...trace, steps: cappedSteps },
    };
    return { ...state, messages: updatedMessages };
  },

  // ---------------------------------------------------- Connector notices
  // Actionable connector failure banners (Lot 3 P3, ADR-134). ADD dedupes by
  // (connectorType, action) — backend emits once per failed step; returning
  // the same array reference on dedup avoids a useless re-render.
  CONNECTOR_NOTICE_ADD: (state, action) => {
    const { notice } = action.payload;
    const exists = state.connectorNotices.some(
      n => n.connectorType === notice.connectorType && n.action === notice.action
    );
    if (exists) return state;
    return { ...state, connectorNotices: [...state.connectorNotices, notice] };
  },

  CONNECTOR_NOTICE_DISMISS: (state, action) => ({
    ...state,
    connectorNotices: state.connectorNotices.filter(
      n => !(n.connectorType === action.payload.connectorType && n.action === action.payload.action)
    ),
  }),

  // ------------------------------------------------------------------ HITL
  // Approval card lifecycle (Lot 1 P1-V1) — see chat-reducer.hitl-card.test.ts
  // for the full transition matrix.
  HITL_AWAITING: (state, action) => ({
    ...state,
    // Last-wins: a fresh interrupt replaces any previous card state
    // (successive interrupts in one logical turn, replay reconstruction).
    hitl: {
      status: 'awaiting',
      payload: action.payload.payload,
      resolution: null,
      submittedAction: null,
    },
  }),

  HITL_SUBMITTING: (state, action) =>
    state.hitl.status === 'awaiting'
      ? {
          ...state,
          hitl: { ...state.hitl, status: 'submitting', submittedAction: action.payload.action },
        }
      : state, // Defensive: ignore double-clicks / clicks after resolution

  HITL_EXPIRED: state =>
    state.hitl.status === 'awaiting' || state.hitl.status === 'submitting'
      ? { ...state, hitl: { ...state.hitl, status: 'expired', submittedAction: null } }
      : state,

  HITL_CLEAR: state => ({ ...state, hitl: initialHitlCardState }),

  ADD_APPROVAL_MESSAGE: (state, action) => ({
    ...state,
    messages: [...state.messages, action.payload.message],
  }),

  REMOVE_APPROVAL_MESSAGE: (state, action) => ({
    ...state,
    messages: state.messages.filter(m => m.id !== action.payload.messageId),
  }),

  // ------------------------------------------------------------------ LARS Registry
  REGISTRY_UPDATE: (state, action) => {
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
  },

  REGISTRY_CLEAR: state => ({
    ...state,
    registry: {},
  }),

  // ------------------------------------------------------------------ Debug Panel
  DEBUG_METRICS_SET: (state, action) => ({
    ...state,
    currentDebugMetrics: action.payload.metrics,
  }),

  DEBUG_METRICS_ADD_TO_HISTORY: (state, action) => {
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
  },

  DEBUG_METRICS_UPDATE: (state, action) => {
    // Merge supplementary metrics (e.g., journal extraction) into current + latest history
    const update = action.payload.metrics;
    const updatedCurrent = state.currentDebugMetrics
      ? { ...state.currentDebugMetrics, ...update }
      : null;
    const updatedHistory =
      state.debugMetricsHistory.length > 0
        ? [
            {
              ...state.debugMetricsHistory[0],
              metrics: { ...state.debugMetricsHistory[0].metrics, ...update },
            },
            ...state.debugMetricsHistory.slice(1),
          ]
        : [];
    return {
      ...state,
      currentDebugMetrics: updatedCurrent,
      debugMetricsHistory: updatedHistory,
    };
  },

  DEBUG_METRICS_CLEAR: state => ({
    ...state,
    currentDebugMetrics: null,
    debugMetricsHistory: [],
  }),

  // ------------------------------------------------------------------ Browser Screenshots
  BROWSER_SCREENSHOT: (state, action) => ({ ...state, browserScreenshot: action.payload }),

  BROWSER_SCREENSHOT_CLEAR: state => ({ ...state, browserScreenshot: null }),

  // ------------------------------------------------------------------ Context-usage pill
  CONTEXT_USAGE_HYDRATE: (state, action) => {
    const { tokens, threshold } = action.payload;
    if (threshold <= 0) {
      return state;
    }
    return {
      ...state,
      contextUsage: {
        tokens,
        threshold,
        ratio: Math.min(1.5, tokens / threshold),
      },
    };
  },

  // ------------------------------------------------------------------ Compaction v2
  STREAM_COMPACTION_START: (state, action) => ({
    ...state,
    status: 'compacting',
    compaction: {
      phase: 'in_progress',
      estimatedDurationSeconds: action.payload.estimatedDurationSeconds,
      strategy: action.payload.strategy,
      startedAt: Date.now(),
    },
  }),

  STREAM_COMPACTION_DONE: (state, action) => ({
    ...state,
    // Compaction is followed by the real LLM response stream; rewind to
    // 'streaming' so the existing token-streaming UX takes over. If a
    // late event arrives in a non-compacting state (defensive), keep the
    // status untouched.
    status: state.status === 'compacting' ? 'streaming' : state.status,
    compaction: {
      phase: action.payload.strategy === 'truncation' ? 'truncated' : 'done',
      tokensSaved: action.payload.tokensSaved,
      durationMs: action.payload.durationMs,
      strategy: action.payload.strategy,
    },
  }),
};

/**
 * Pure reducer function for chat state management.
 *
 * @param state - Current chat state
 * @param action - Action to apply
 * @returns New chat state (immutable)
 */
export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  // The mapped-type table guarantees a handler exists for every action.type;
  // the indexed access loses the per-member action narrowing, so the handler
  // is invoked through a widened signature (safe: table keys ≡ action types).
  // The `?? state` fallback preserves the former `default:` branch for an
  // out-of-contract action dispatched at runtime (e.g. an untyped test).
  const handler = ACTION_HANDLERS[action.type] as
    | ((s: ChatState, a: ChatAction) => ChatState)
    | undefined;
  return handler ? handler(state, action) : state;
}

// SEC-035: the key lives in lib/constants so the logout purge registry
// (client-storage-purge.ts) and this reducer can never drift apart.
const DEBUG_HISTORY_STORAGE_KEY = DEBUG_METRICS_HISTORY_KEY;
/** Keep only the N most recent entries to avoid filling sessionStorage (5 MB limit). */
const DEBUG_HISTORY_MAX_ENTRIES = 50;

/**
 * Helper to create initial state, hydrating debug metrics history from sessionStorage.
 */
export function createInitialState(): ChatState {
  let debugMetricsHistory: ChatState['debugMetricsHistory'] = [];
  if (typeof window !== 'undefined') {
    try {
      const stored = sessionStorage.getItem(DEBUG_HISTORY_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        debugMetricsHistory = Array.isArray(parsed) ? parsed.slice(-DEBUG_HISTORY_MAX_ENTRIES) : [];
      }
    } catch {
      // Ignore parse errors — start fresh
    }
  }
  return { ...initialChatState, debugMetricsHistory };
}

/**
 * Persist debug metrics history to sessionStorage.
 * Called from useChat via useEffect to keep reducer pure.
 * Truncates to the most recent DEBUG_HISTORY_MAX_ENTRIES entries.
 */
export function persistDebugMetricsHistory(history: ChatState['debugMetricsHistory']): void {
  if (typeof window === 'undefined') return;
  try {
    const trimmed = history.slice(-DEBUG_HISTORY_MAX_ENTRIES);
    sessionStorage.setItem(DEBUG_HISTORY_STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // sessionStorage full or unavailable — ignore
  }
}

/**
 * SSE Handlers Module for useChat.ts.
 *
 * Provides a centralized handler map for all SSE event types.
 * This reduces useChat.ts complexity by ~400 lines.
 *
 * Usage:
 *   import { processSSEChunk, SSEHandlerContext } from '@/lib/sse-handlers';
 */

import { ChatStreamChunk, SSEChunkType } from '@/types/chat';
import { logger } from '@/lib/logger';
import { SSEHandlerContext, SSEHandlerMap } from './types';
import {
  // Data handlers
  handleRegistryUpdate,
  handleDebugMetrics,
  handleDebugMetricsUpdate,
  // Progress handlers
  handleRouterDecision,
  handlePlannerMetadata,
  handleExecutionStep,
  // Streaming handlers
  handleToken,
  handleContentReplacement,
  handleDone,
  // HITL handlers
  handleHitlInterruptMetadata,
  handleHitlQuestionToken,
  handleHitlInterruptComplete,
  handleHitlInterruptLegacy,
  // Voice handlers
  handleVoiceCommentStart,
  handleVoiceAudioChunk,
  handleVoiceComplete,
  handleVoiceError,
  // Browser screenshot handler
  handleBrowserScreenshot,
  // Error handler
  handleError,
  // Helper
  getProgressMessage,
} from './handlers';

// Re-export types
export type { SSEHandlerContext, SSEHandler, ProgressMessageMetadata } from './types';

// Re-export helper
export { getProgressMessage };

/**
 * Map of SSE chunk types to their handler functions.
 * Covers all 17 event types from the backend.
 */
const SSE_HANDLERS: SSEHandlerMap = {
  // Data events
  registry_update: handleRegistryUpdate,
  debug_metrics: handleDebugMetrics,
  debug_metrics_update: handleDebugMetricsUpdate,

  // Progress feedback events
  router_decision: handleRouterDecision,
  planner_metadata: handlePlannerMetadata,
  execution_step: handleExecutionStep,

  // Streaming events
  token: handleToken,
  content_replacement: handleContentReplacement,
  done: handleDone,

  // HITL events
  hitl_interrupt_metadata: handleHitlInterruptMetadata,
  hitl_question_token: handleHitlQuestionToken,
  hitl_interrupt_complete: handleHitlInterruptComplete,
  hitl_interrupt: handleHitlInterruptLegacy, // Legacy

  // Voice TTS events
  voice_comment_start: handleVoiceCommentStart,
  voice_audio_chunk: handleVoiceAudioChunk,
  voice_complete: handleVoiceComplete,
  voice_error: handleVoiceError,

  // Browser screenshot events
  browser_screenshot: handleBrowserScreenshot,

  // Error events
  error: handleError,
};

// ============================================================================
// Token batching (perceived-latency optimization)
// ============================================================================
// Each raw SSE token used to trigger its own dispatch → React re-render →
// full remark/rehype (+KaTeX) re-parse of the ENTIRE accumulated message.
// For an N-token answer that is O(N²) parsing work on the main thread.
// Tokens are now coalesced and flushed at most once per animation frame
// (~60fps — well above text-reading perception). Ordering is preserved:
// any NON-token chunk synchronously flushes the buffer before being handled,
// so replacements, done, HITL and error events never overtake buffered text.

let pendingTokens: string[] = [];
let pendingTokenContext: SSEHandlerContext | null = null;
let tokenFlushHandle: number | null = null;

/** Flush buffered tokens as a single aggregated token chunk (order-safe). */
function flushPendingTokens(): void {
  if (tokenFlushHandle !== null && typeof cancelAnimationFrame !== 'undefined') {
    cancelAnimationFrame(tokenFlushHandle);
  }
  tokenFlushHandle = null;

  if (pendingTokens.length === 0 || pendingTokenContext === null) {
    pendingTokens = [];
    pendingTokenContext = null;
    return;
  }

  const content = pendingTokens.join('');
  // The most recent context is always current: any non-token chunk flushes
  // BEFORE its handler runs, so no context mutation can be missed here.
  const context = pendingTokenContext;
  pendingTokens = [];
  pendingTokenContext = null;

  handleToken({ type: 'token', content } as ChatStreamChunk, context);
}

/**
 * Flush any buffered tokens immediately (public entry point).
 *
 * Called on stream error: tokens received BEFORE the error were visible in
 * the pre-batching behavior, so they are dispatched now — and doing it
 * synchronously prevents a late animation-frame flush from dispatching a
 * STREAM_TOKEN after the SSE_ERROR state transition.
 */
export function flushTokenBatching(): void {
  flushPendingTokens();
}

/**
 * Reset the token batcher (drops any buffered tokens WITHOUT dispatching).
 *
 * Must be called when a new stream starts: a late animation-frame flush from
 * a cancelled stream must never inject stale tokens into the next message.
 */
export function resetTokenBatching(): void {
  if (tokenFlushHandle !== null && typeof cancelAnimationFrame !== 'undefined') {
    cancelAnimationFrame(tokenFlushHandle);
  }
  tokenFlushHandle = null;
  pendingTokens = [];
  pendingTokenContext = null;
}

/**
 * Process an SSE chunk by dispatching to the appropriate handler.
 *
 * @param chunk - The SSE chunk to process
 * @param context - Handler context with dispatch, refs, and callbacks
 */
export function processSSEChunk(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  if (chunk.type === 'token') {
    // Buffer instead of dispatching per token. Empty tokens are dropped
    // (they only produced no-op renders before).
    if (typeof chunk.content === 'string' && chunk.content) {
      pendingTokens.push(chunk.content);
      pendingTokenContext = context;
      if (tokenFlushHandle === null) {
        if (typeof requestAnimationFrame === 'undefined') {
          // SSR/test environments without rAF: degrade to synchronous dispatch
          flushPendingTokens();
        } else {
          tokenFlushHandle = requestAnimationFrame(() => {
            tokenFlushHandle = null;
            flushPendingTokens();
          });
        }
      }
    }
    return;
  }

  // Any non-token chunk: flush buffered tokens first (ordering guarantee)
  flushPendingTokens();

  const handler = SSE_HANDLERS[chunk.type];

  if (handler) {
    handler(chunk, context);
  } else {
    // Log unknown event types for debugging
    logger.debug('sse_unknown_event_type', {
      type: chunk.type,
      hasContent: !!chunk.content,
      hasMetadata: !!chunk.metadata,
    });
  }
}

/**
 * Check if an SSE chunk type has a registered handler.
 *
 * @param type - SSE chunk type to check
 * @returns True if a handler exists
 */
export function hasSSEHandler(type: SSEChunkType | string): boolean {
  return type in SSE_HANDLERS;
}

/**
 * Get all registered SSE handler types.
 *
 * @returns Array of registered handler type names
 */
export function getRegisteredSSEHandlers(): string[] {
  return Object.keys(SSE_HANDLERS);
}

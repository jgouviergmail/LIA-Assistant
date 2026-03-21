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

  // Error events
  error: handleError,
};

/**
 * Process an SSE chunk by dispatching to the appropriate handler.
 *
 * @param chunk - The SSE chunk to process
 * @param context - Handler context with dispatch, refs, and callbacks
 */
export function processSSEChunk(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
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

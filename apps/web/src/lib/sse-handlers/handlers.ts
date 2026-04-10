/**
 * SSE Event Handlers for useChat.ts.
 *
 * Extracted from useChat.ts to reduce file size and improve maintainability.
 * Each handler processes a specific SSE chunk type from the chat stream.
 */

import { toast } from 'sonner';
import { logger } from '@/lib/logger';
import { generateFallbackHitlQuestion } from '@/lib/hitl-utils';
import { generateUUID } from '@/lib/utils';
import { usePsycheStore } from '@/stores/psycheStore';
import type { PsycheStateSummary } from '@/types/psyche';
import {
  ChatStreamChunk,
  DoneMetadata,
  ToolApprovalMetadata,
  RegistryUpdateMetadata,
  DebugMetrics,
  VoiceAudioChunk,
  BrowserScreenshotData,
} from '@/types/chat';
import { DebugMetricsEntry } from '@/types/chat-state';
import { SSEHandlerContext, ProgressMessageMetadata } from './types';

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Maximum number of execution steps to display before collapsing older ones.
 */
const MAX_VISIBLE_STEPS = 10;

/**
 * Pick a random phrase from the i18n analyzingMessages array.
 * Used only for the initial router_decision step to add a touch of personality.
 */
function getRandomAnalyzingMessage(t: SSEHandlerContext['t']): string {
  const messages = t('hitl.progress.analyzingMessages', { returnObjects: true });
  if (Array.isArray(messages) && messages.length > 0) {
    const randomIndex = Math.floor(Math.random() * messages.length);
    return messages[randomIndex];
  }
  return t('hitl.progress.analyzing');
}

/**
 * Get user-facing progress message based on SSE event type.
 * Maps backend events to localized, user-friendly messages.
 */
export function getProgressMessage(
  eventType: string,
  t: SSEHandlerContext['t'],
  metadata?: ProgressMessageMetadata
): string {
  switch (eventType) {
    case 'router_decision':
      return getRandomAnalyzingMessage(t);
    case 'planner_metadata':
      return `*📋 ${t('execution.steps.planner_generation', { defaultValue: 'Planning...' })}*`;
    case 'hitl_interrupt_metadata':
      return t('hitl.validating_access');
    case 'execution_step':
      if (metadata?.emoji && metadata?.i18n_key) {
        const stepText = t(`execution.steps.${metadata.i18n_key}`, { defaultValue: '' });
        if (stepText) {
          return `*${metadata.emoji} ${stepText}*`;
        }
      }
      // Fallback: use detail if available (e.g., reasoning snippet)
      if (metadata?.detail) {
        const emoji = metadata.emoji || '🧠';
        const truncated =
          metadata.detail.length > 80 ? metadata.detail.slice(0, 77) + '...' : metadata.detail;
        return `*${emoji} ${truncated}*`;
      }
      return t('hitl.progress.thinking');
    default:
      return t('hitl.progress.thinking');
  }
}

/**
 * Build the full accumulated steps display content.
 * Caps at MAX_VISIBLE_STEPS with a "... N previous steps" indicator.
 */
function buildAccumulatedStepsContent(steps: string[], t: SSEHandlerContext['t']): string {
  if (steps.length <= MAX_VISIBLE_STEPS) {
    return steps.join('\n');
  }
  const hidden = steps.length - MAX_VISIBLE_STEPS;
  return [
    `*... ${hidden} ${t('execution.steps.previous_steps', { count: hidden, defaultValue: 'previous steps' })}*`,
    ...steps.slice(-MAX_VISIBLE_STEPS),
  ].join('\n');
}

// ============================================================================
// Data Event Handlers
// ============================================================================

/**
 * Handle registry_update: LARS registry data arrives BEFORE tokens
 */
export function handleRegistryUpdate(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { dispatch, withContext } = context;
  const registryMetadata = chunk.metadata as RegistryUpdateMetadata;

  if (registryMetadata?.items && typeof registryMetadata.items === 'object') {
    dispatch({
      type: 'REGISTRY_UPDATE',
      payload: { items: registryMetadata.items },
    });

    logger.debug(
      'chat_registry_update',
      withContext({
        component: 'useChat',
        item_count: registryMetadata.count || Object.keys(registryMetadata.items).length,
        item_types: [...new Set(Object.values(registryMetadata.items).map(item => item.type))],
      })
    );
  } else {
    logger.warn(
      'chat_registry_update_invalid',
      withContext({
        component: 'useChat',
        metadata: chunk.metadata,
      })
    );
  }
}

/**
 * Handle debug_metrics: Scoring metrics for debug panel (DEBUG=true only)
 *
 * Sets current metrics for real-time display and adds to cumulative history
 * for collapsible request-by-request comparison.
 */
export function handleDebugMetrics(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { dispatch, withContext } = context;
  const debugMetricsData = chunk.metadata as DebugMetrics;

  if (debugMetricsData) {
    // Set current metrics for real-time display
    dispatch({
      type: 'DEBUG_METRICS_SET',
      payload: { metrics: debugMetricsData },
    });

    // Add to cumulative history for collapsible display
    // Extract query from query_info for the history entry header
    const originalQuery = debugMetricsData.query_info?.original_query || 'Unknown query';

    const historyEntry: DebugMetricsEntry = {
      id: generateUUID(),
      timestamp: new Date(),
      query: originalQuery,
      metrics: debugMetricsData,
    };

    dispatch({
      type: 'DEBUG_METRICS_ADD_TO_HISTORY',
      payload: { entry: historyEntry },
    });

    logger.debug(
      'chat_debug_metrics',
      withContext({
        component: 'useChat',
        route_to: debugMetricsData.routing_decision?.route_to,
        domains: debugMetricsData.domain_selection?.selected_domains,
        intent: debugMetricsData.intent_detection?.detected_intent,
        history_entry_id: historyEntry.id,
      })
    );
  }
}

/**
 * Handle debug_metrics_update: Supplementary debug metrics (post-background tasks)
 *
 * Merges additional metrics (e.g., journal extraction results) into the
 * current debug metrics and the most recent history entry.
 * Emitted after background tasks complete (after await_run_id_tasks).
 */
export function handleDebugMetricsUpdate(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { dispatch, withContext } = context;
  const updateData = chunk.metadata as Partial<DebugMetrics>;

  if (updateData) {
    dispatch({
      type: 'DEBUG_METRICS_UPDATE',
      payload: { metrics: updateData },
    });

    logger.debug(
      'chat_debug_metrics_update',
      withContext({
        component: 'useChat',
        keys: Object.keys(updateData),
      })
    );
  }
}

// ============================================================================
// Progress Feedback Handlers
// ============================================================================

/**
 * Handle router_decision: First progress feedback (~1s after send)
 */
export function handleRouterDecision(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const {
    dispatch,
    withContext,
    t,
    assistantMessageId,
    progressMessageId,
    setProgressMessageId,
    executionStepsRef,
  } = context;

  logger.debug(
    'chat_router_decision',
    withContext({
      component: 'useChat',
      metadata: chunk.metadata,
    })
  );

  dispatch({
    type: 'ROUTER_DECISION',
    payload: chunk.metadata as {
      intention: string;
      confidence: number;
      context_label: string;
      next_node: string;
      reasoning?: string | null;
    },
  });

  // Transition to connected state
  dispatch({ type: 'SSE_CONNECTED' });

  // Reset accumulated steps and add router as first step
  executionStepsRef.current = [];
  context.emittedStepKeysRef.current = new Set();
  const routerStep = getProgressMessage('router_decision', t);
  executionStepsRef.current.push(routerStep);
  context.emittedStepKeysRef.current.add('router_decision');
  const fullContent = buildAccumulatedStepsContent(executionStepsRef.current, t);

  if (!progressMessageId) {
    // First progress event - create message
    setProgressMessageId(assistantMessageId);
    dispatch({
      type: 'STREAM_START',
      payload: {
        messageId: assistantMessageId,
        initialContent: fullContent,
      },
    });
  } else {
    // Update existing progress message
    dispatch({
      type: 'STREAM_REPLACE',
      payload: { content: fullContent },
    });
  }
}

/**
 * Handle planner_metadata: Planning progress (~2s after send)
 */
export function handlePlannerMetadata(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const {
    dispatch,
    withContext,
    t,
    progressMessageId,
    setProgressMessageId,
    assistantMessageId,
    executionStepsRef,
    emittedStepKeysRef,
  } = context;

  logger.info(
    'chat_planner_metadata',
    withContext({
      component: 'useChat',
      metadata: chunk.metadata,
    })
  );

  // Accumulate planner step and register for dedup
  const plannerStep = getProgressMessage('planner_metadata', t);
  executionStepsRef.current.push(plannerStep);
  emittedStepKeysRef.current.add('planner_generation');
  const fullContent = buildAccumulatedStepsContent(executionStepsRef.current, t);

  if (progressMessageId) {
    dispatch({
      type: 'STREAM_REPLACE',
      payload: { content: fullContent },
    });
  } else {
    // Edge case: planner_metadata arrived before router_decision
    setProgressMessageId(assistantMessageId);
    dispatch({
      type: 'STREAM_START',
      payload: {
        messageId: assistantMessageId,
        initialContent: fullContent,
      },
    });
  }
}

/**
 * Handle execution_step: Dynamic execution progress messages (accumulated)
 */
export function handleExecutionStep(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const {
    dispatch,
    withContext,
    t,
    progressMessageId,
    setProgressMessageId,
    assistantMessageId,
    executionStepsRef,
    emittedStepKeysRef,
  } = context;

  logger.debug(
    'chat_execution_step',
    withContext({
      component: 'useChat',
      metadata: chunk.metadata,
    })
  );

  const metadata = chunk.metadata as ProgressMessageMetadata | undefined;

  // Deduplication by i18n_key: skip if already emitted by router/planner handlers.
  // This prevents duplicates between router_decision/planner_metadata handlers and
  // execution_step events from the backend "updates" stream mode.
  if (metadata?.i18n_key && emittedStepKeysRef.current.has(metadata.i18n_key)) {
    return; // Already shown by router/planner handler
  }

  // Build and accumulate step message
  const stepMessage = getProgressMessage('execution_step', t, metadata);
  executionStepsRef.current.push(stepMessage);
  if (metadata?.i18n_key) {
    emittedStepKeysRef.current.add(metadata.i18n_key);
  }
  const fullContent = buildAccumulatedStepsContent(executionStepsRef.current, t);

  if (progressMessageId) {
    dispatch({
      type: 'STREAM_REPLACE',
      payload: { content: fullContent },
    });
  } else {
    // Edge case: execution_step arrived before router_decision
    setProgressMessageId(assistantMessageId);
    dispatch({
      type: 'STREAM_START',
      payload: {
        messageId: assistantMessageId,
        initialContent: fullContent,
      },
    });
  }
}

// ============================================================================
// Streaming Event Handlers
// ============================================================================

/**
 * Handle token: Normal streaming token
 */
export function handleToken(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const {
    dispatch,
    assistantMessageId,
    progressMessageId,
    setProgressMessageId,
    normalStreamInitialized,
    setNormalStreamInitialized,
    executionStepsRef,
  } = context;

  if (progressMessageId && !normalStreamInitialized) {
    // Clear accumulated execution steps — real content is arriving
    executionStepsRef.current = [];
    context.emittedStepKeysRef.current = new Set();
    // Progress message exists → replace with first token
    dispatch({
      type: 'STREAM_REPLACE',
      payload: { content: chunk.content },
    });
    setNormalStreamInitialized(true);
    setProgressMessageId(null); // Progress phase complete
  } else if (!normalStreamInitialized) {
    // No progress message (backwards compatible) → create new message
    dispatch({ type: 'STREAM_START', payload: { messageId: assistantMessageId } });
    setNormalStreamInitialized(true);
    // Accumulate first streaming token
    dispatch({ type: 'STREAM_TOKEN', payload: { token: chunk.content } });
  } else {
    // Normal case: stream already initialized, accumulate token
    dispatch({ type: 'STREAM_TOKEN', payload: { token: chunk.content } });
  }
}

/**
 * Handle content_replacement: Post-processed content replacement
 *
 * When content_final_replacement is set (e.g., HTML cards), the backend skips
 * streaming tokens entirely and sends only this replacement. In that case,
 * no message container exists yet — we must create one first via STREAM_START.
 * This happens in ReAct mode where the response LLM tokens are skipped.
 */
export function handleContentReplacement(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const {
    dispatch,
    assistantMessageId,
    normalStreamInitialized,
    setNormalStreamInitialized,
    progressMessageId,
    setProgressMessageId,
    executionStepsRef,
  } = context;

  // Ensure a message container exists AND currentMessageId is set before replacing.
  // STREAM_START is idempotent in the reducer — if the message already exists
  // (e.g., created by router progress), it just re-sets currentMessageId.
  // This guarantees STREAM_REPLACE always has a valid target, regardless of
  // whether progress events fired, or currentMessageId was cleared by an
  // intermediate event.
  if (!normalStreamInitialized) {
    // Clear accumulated execution steps — real content is arriving
    executionStepsRef.current = [];
    context.emittedStepKeysRef.current = new Set();
    dispatch({ type: 'STREAM_START', payload: { messageId: assistantMessageId } });
    setNormalStreamInitialized(true);
    if (progressMessageId) {
      setProgressMessageId(null);
    }
  }

  dispatch({
    type: 'STREAM_REPLACE',
    payload: { content: chunk.content as string },
  });
}

/**
 * Handle done: Stream completion
 */
export function handleDone(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { dispatch, withContext, assistantMessageId } = context;
  const metadata = chunk.metadata as DoneMetadata | undefined;

  logger.info(
    'chat_stream_done',
    withContext({
      component: 'useChat',
      metadata: chunk.metadata,
    })
  );

  // Psyche Engine: Push mood state into Zustand store from SSE done metadata
  if (metadata?.psyche_state) {
    usePsycheStore.getState().updateFromSSE(metadata.psyche_state as PsycheStateSummary);
  }

  dispatch({
    type: 'STREAM_DONE',
    payload: {
      messageId: assistantMessageId,
      metadata,
    },
  });
}

// ============================================================================
// HITL Event Handlers
// ============================================================================

/**
 * Handle hitl_interrupt_metadata: HITL detected (~8s after send)
 */
export function handleHitlInterruptMetadata(
  chunk: ChatStreamChunk,
  context: SSEHandlerContext
): void {
  const {
    dispatch,
    withContext,
    t,
    hitlQuestionBuffer,
    progressMessageId,
    setProgressMessageId,
    executionStepsRef,
  } = context;

  const metadataChunk = chunk.metadata as ToolApprovalMetadata & {
    message_id: string;
  };
  const messageId = metadataChunk.message_id || `hitl_${generateUUID()}`;

  logger.info(
    'chat_hitl_interrupt_metadata',
    withContext({
      component: 'useChat',
      message_id: messageId,
      action_requests_count: metadataChunk?.action_requests?.length,
    })
  );

  // Initialize buffer for this question
  hitlQuestionBuffer.current.set(messageId, '');

  // Clear accumulated execution steps — HITL takes over the UI
  executionStepsRef.current = [];
  context.emittedStepKeysRef.current = new Set();

  // Update ephemeral progress message to HITL state
  const hitlMessage = getProgressMessage('hitl_interrupt_metadata', t);

  if (progressMessageId) {
    // Update existing progress message (router → planner → HITL)
    dispatch({
      type: 'STREAM_REPLACE',
      payload: { content: hitlMessage },
    });
  } else {
    // Fallback: create message if router/planner didn't fire (edge case)
    setProgressMessageId(messageId);
    dispatch({
      type: 'STREAM_START',
      payload: {
        messageId: messageId,
        initialContent: hitlMessage,
      },
    });
  }
}

/**
 * Handle hitl_question_token: Progressive token rendering
 */
export function handleHitlQuestionToken(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { dispatch, withContext, hitlQuestionBuffer } = context;

  const tokenChunk = chunk.metadata as { message_id: string };
  const tokenMessageId = tokenChunk.message_id;
  const token = chunk.content;

  // Skip truly empty tokens (but not whitespace)
  if (!tokenMessageId || token === undefined || token === null || token === '') {
    return;
  }

  // Accumulate token in buffer
  const currentBuffer = hitlQuestionBuffer.current.get(tokenMessageId) || '';
  const isFirstToken = currentBuffer === '';
  hitlQuestionBuffer.current.set(tokenMessageId, currentBuffer + token);

  // For first token, replace placeholder entirely
  // For subsequent tokens, just append
  if (isFirstToken) {
    dispatch({ type: 'STREAM_REPLACE', payload: { content: token } });
  } else {
    dispatch({ type: 'STREAM_TOKEN', payload: { token } });
  }

  logger.debug(
    'chat_hitl_question_token',
    withContext({
      component: 'useChat',
      message_id: tokenMessageId,
      token_length: token.length,
      is_first_token: isFirstToken,
    })
  );
}

/**
 * Handle hitl_interrupt_complete: Finalize HITL message
 */
export function handleHitlInterruptComplete(
  chunk: ChatStreamChunk,
  context: SSEHandlerContext
): void {
  const { dispatch, withContext, t, hitlQuestionBuffer } = context;

  const completeChunk = chunk.metadata as ToolApprovalMetadata & {
    message_id: string;
    generated_question?: string;
  };
  const completeMessageId = completeChunk.message_id;

  // Get buffered question or fallback to metadata/template
  let finalQuestion = hitlQuestionBuffer.current.get(completeMessageId) || '';

  // Fallback 1: Use generated_question from metadata if buffer empty
  if (!finalQuestion && completeChunk.generated_question) {
    finalQuestion = completeChunk.generated_question;
    dispatch({ type: 'STREAM_TOKEN', payload: { token: finalQuestion } });
  }

  // Fallback 2: Generate template question if still empty
  if (!finalQuestion && completeChunk.action_requests) {
    finalQuestion = generateFallbackHitlQuestion(completeChunk.action_requests, t);
    dispatch({ type: 'STREAM_TOKEN', payload: { token: finalQuestion } });

    logger.warn(
      'chat_hitl_fallback_question_used',
      withContext({
        component: 'useChat',
        message_id: completeMessageId,
        reason: 'streaming_failed_or_empty',
      })
    );
  }

  // Finalize stream without token metadata (HITL tokens are partial/misleading)
  dispatch({
    type: 'STREAM_DONE',
    payload: {
      messageId: completeMessageId,
      metadata: {},
    },
  });

  // Cleanup buffer
  hitlQuestionBuffer.current.delete(completeMessageId);

  logger.info(
    'chat_hitl_question_complete',
    withContext({
      component: 'useChat',
      message_id: completeMessageId,
      question_length: finalQuestion.length,
      fallback_used: !hitlQuestionBuffer.current.has(completeMessageId),
    })
  );
}

/**
 * Handle hitl_interrupt: Legacy non-streaming HITL handler
 */
export function handleHitlInterruptLegacy(
  chunk: ChatStreamChunk,
  context: SSEHandlerContext
): void {
  const { dispatch, withContext, t } = context;
  const legacyHitlMetadata = chunk.metadata as ToolApprovalMetadata;

  logger.warn(
    'chat_hitl_interrupt_legacy',
    withContext({
      component: 'useChat',
      message: 'Received old hitl_interrupt type (non-streaming). Consider backend upgrade.',
      action_requests_count: legacyHitlMetadata?.action_requests?.length,
    })
  );

  const legacyQuestion =
    legacyHitlMetadata.generated_question ||
    generateFallbackHitlQuestion(legacyHitlMetadata.action_requests || [], t);

  const legacyMessageId = `hitl_${generateUUID()}`;
  dispatch({ type: 'STREAM_START', payload: { messageId: legacyMessageId } });
  dispatch({ type: 'STREAM_TOKEN', payload: { token: legacyQuestion } });
  dispatch({ type: 'STREAM_DONE', payload: { messageId: legacyMessageId } });
}

// ============================================================================
// Voice TTS Event Handlers
// ============================================================================

/**
 * Handle voice_comment_start: Voice playback starting
 */
export function handleVoiceCommentStart(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { withContext } = context;
  logger.debug(
    'chat_voice_comment_start',
    withContext({
      component: 'useChat',
      run_id: (chunk.metadata as Record<string, unknown>)?.run_id,
    })
  );
}

/**
 * Handle voice_audio_chunk: Stream audio chunk to playback queue
 */
export function handleVoiceAudioChunk(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { handleVoiceChunk, withContext } = context;
  const audioChunk = chunk.content as unknown as VoiceAudioChunk;

  if (audioChunk?.audio_base64) {
    handleVoiceChunk(audioChunk);
    logger.debug(
      'chat_voice_audio_chunk',
      withContext({
        component: 'useChat',
        phrase_index: audioChunk.phrase_index,
        is_last: audioChunk.is_last,
      })
    );
  }
}

/**
 * Handle voice_complete: Voice playback completed
 */
export function handleVoiceComplete(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { withContext } = context;
  logger.info(
    'chat_voice_complete',
    withContext({
      component: 'useChat',
      chunk_count: (chunk.metadata as Record<string, unknown>)?.chunk_count,
    })
  );
}

/**
 * Handle voice_error: Graceful degradation for voice errors
 */
export function handleVoiceError(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { withContext } = context;
  logger.warn(
    'chat_voice_error',
    withContext({
      component: 'useChat',
      error: chunk.content,
      error_type: (chunk.metadata as Record<string, unknown>)?.error_type,
    })
  );
}

// ============================================================================
// Browser Screenshot Event Handler
// ============================================================================

/**
 * Handle browser_screenshot: Progressive screenshot overlay during browsing
 */
export function handleBrowserScreenshot(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { dispatch, withContext } = context;
  const screenshotData = chunk.content as unknown as BrowserScreenshotData;

  if (screenshotData?.image_base64) {
    dispatch({ type: 'BROWSER_SCREENSHOT', payload: screenshotData });
    logger.debug(
      'chat_browser_screenshot',
      withContext({
        component: 'useChat',
        url: screenshotData.url?.slice(0, 100),
      })
    );
  }
}

// ============================================================================
// Error Event Handler
// ============================================================================

/**
 * Handle error: Stream error
 */
export function handleError(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { dispatch, withContext } = context;
  const metadata = chunk.metadata as Record<string, unknown> | null;
  const errorCode = metadata?.error_code as string | undefined;

  // Usage limit exceeded — show specific toast (from Layer 1/2 enforcement)
  if (errorCode === 'usage_limit_exceeded') {
    toast.error(chunk.content || 'Usage limit exceeded');
  }

  logger.error(
    'chat_stream_error',
    new Error(chunk.content),
    withContext({
      component: 'useChat',
      error_code: errorCode,
    })
  );

  dispatch({
    type: 'STREAM_ERROR',
    payload: { error: chunk.content },
  });
}

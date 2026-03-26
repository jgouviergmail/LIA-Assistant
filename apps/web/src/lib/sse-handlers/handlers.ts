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
 * Get a random analyzing message from the translated array.
 * Falls back to the static 'analyzing' key if array is not available.
 */
function getRandomAnalyzingMessage(t: SSEHandlerContext['t']): string {
  const messages = t('hitl.progress.analyzingMessages', { returnObjects: true });

  // Check if we got an array back
  if (Array.isArray(messages) && messages.length > 0) {
    const randomIndex = Math.floor(Math.random() * messages.length);
    return messages[randomIndex];
  }

  // Fallback to static message if array is not available
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
      return t('hitl.progress.planning');
    case 'hitl_interrupt_metadata':
      return t('hitl.validating_access');
    case 'execution_step':
      if (metadata?.emoji && metadata?.i18n_key) {
        return `*${metadata.emoji} ${t(`execution.steps.${metadata.i18n_key}`)}*`;
      }
      return t('hitl.progress.thinking');
    default:
      return t('hitl.progress.thinking');
  }
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
  const { dispatch, withContext, t, assistantMessageId, progressMessageId, setProgressMessageId } =
    context;

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

  // Create or update ephemeral progress message
  const routerMessage = getProgressMessage('router_decision', t);

  if (!progressMessageId) {
    // First progress event - create message
    setProgressMessageId(assistantMessageId);
    dispatch({
      type: 'STREAM_START',
      payload: {
        messageId: assistantMessageId,
        initialContent: routerMessage,
      },
    });
  } else {
    // Update existing progress message
    dispatch({
      type: 'STREAM_REPLACE',
      payload: { content: routerMessage },
    });
  }
}

/**
 * Handle planner_metadata: Planning progress (~2s after send)
 */
export function handlePlannerMetadata(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { dispatch, withContext, t, progressMessageId } = context;

  logger.info(
    'chat_planner_metadata',
    withContext({
      component: 'useChat',
      metadata: chunk.metadata,
    })
  );

  // Update ephemeral progress message
  const plannerMessage = getProgressMessage('planner_metadata', t);

  if (progressMessageId) {
    dispatch({
      type: 'STREAM_REPLACE',
      payload: { content: plannerMessage },
    });
  }
}

/**
 * Handle execution_step: Dynamic execution progress messages
 */
export function handleExecutionStep(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { dispatch, withContext, t, progressMessageId } = context;

  logger.debug(
    'chat_execution_step',
    withContext({
      component: 'useChat',
      metadata: chunk.metadata,
    })
  );

  // Update ephemeral progress message with execution step
  const executionMessage = getProgressMessage(
    'execution_step',
    t,
    chunk.metadata as ProgressMessageMetadata | undefined
  );

  if (progressMessageId) {
    dispatch({
      type: 'STREAM_REPLACE',
      payload: { content: executionMessage },
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
  } = context;

  if (progressMessageId && !normalStreamInitialized) {
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
 */
export function handleContentReplacement(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  const { dispatch } = context;
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
  const { dispatch, withContext, t, hitlQuestionBuffer, progressMessageId, setProgressMessageId } =
    context;

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

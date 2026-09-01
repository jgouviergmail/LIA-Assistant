/**
 * SSE Event Handlers for useChat.ts.
 *
 * Extracted from useChat.ts to reduce file size and improve maintainability.
 * Each handler processes a specific SSE chunk type from the chat stream.
 */

import { toast } from 'sonner';
import { logger } from '@/lib/logger';
import { generateFallbackHitlQuestion } from '@/lib/hitl-utils';
import { normalizeHitlPayload } from '@/lib/hitl-payload';
import { generateUUID } from '@/lib/utils';
import { parseToneAnnotation } from '@/components/eyes/tone';
import { usePsycheStore } from '@/stores/psycheStore';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
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
import type { ExecutionTrace, ExecutionTraceStep } from '@/types/execution-trace';
import { SSEHandlerContext, ProgressMessageMetadata } from './types';

// Stable id used to morph the compaction toast in place (loading → success/warn)
// rather than stacking distinct toasts.
const COMPACTION_TOAST_ID = 'compaction-progress';

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

/** Escape HTML so the model's reasoning text can't inject markup (rehype-raw). */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Render the live reasoning (💭) block as a `lia-reasoning` HTML sentinel.
 *
 * The raw reasoning is free-form prose split into paragraphs by blank lines
 * (the actual shape emitted by the models — no markdown headers/lists). We
 * split on blank lines, flatten internal single newlines to spaces (so
 * sentences are never cut mid-phrase), HTML-escape each paragraph, and emit a
 * `<div class="lia-reasoning">` containing one `<p>` per paragraph plus a
 * header line. MarkdownContent renders this div via the <ReasoningScroll>
 * component (fixed-height, auto-scrolling container — smooth, no jump).
 *
 * Append-only by design: paragraphs are never dropped mid-stream; the container
 * scrolls instead. Total length is bounded by the backend per-node cap and the
 * whole block is wiped on the first answer token. Returns '' when empty.
 */
function buildReasoningBlock(reasoning: string, t: SSEHandlerContext['t']): string {
  const text = reasoning.trim();
  if (!text) return '';

  const paragraphs = text
    .split(/\n\s*\n/)
    .map(p => p.replace(/\s*\n\s*/g, ' ').trim())
    .filter(p => p.length > 0);

  const title = escapeHtml(t('execution.reasoning.title', { defaultValue: 'Reasoning' }));
  const header = `<p class="lia-reasoning__title">💭 ${title}</p>`;
  const body = paragraphs.map(p => `<p>${escapeHtml(p)}</p>`).join('');
  // Blank lines around the div ensure rehype-raw treats it as a block.
  return `\n\n<div class="lia-reasoning">${header}${body}</div>\n\n`;
}

/** Valid trace-step categories (defaults to 'system' for unknown values). */
const TRACE_CATEGORIES = new Set(['system', 'agent', 'tool', 'context']);

/**
 * Build a structured trace step (Lot 2 P2-V1) from execution-step metadata.
 *
 * Reuses the same translated ``execution.steps.<i18n_key>`` labels the live
 * progress bubble shows (already i18n ×6), so the retained trace matches what
 * the user saw. Returns null for a reasoning sub-event (kept separately) or
 * when no meaningful label can be resolved.
 */
function buildTraceStep(
  metadata: ProgressMessageMetadata | undefined,
  t: SSEHandlerContext['t']
): ExecutionTraceStep | null {
  // The caller (handleExecutionStep) already filters reasoning sub-events, so
  // metadata here is either absent or a real step — no reasoning re-check.
  if (!metadata) return null;
  const emoji = metadata.emoji || '⚙️';
  const rawCategory = metadata.category;
  const category =
    typeof rawCategory === 'string' && TRACE_CATEGORIES.has(rawCategory)
      ? (rawCategory as ExecutionTraceStep['category'])
      : 'system';

  let label: string | undefined;
  if (metadata.i18n_key) {
    const translated = t(`execution.steps.${metadata.i18n_key}`, { defaultValue: '' });
    if (translated) label = translated;
  }
  if (!label && metadata.detail) {
    label = metadata.detail.length > 80 ? `${metadata.detail.slice(0, 77)}...` : metadata.detail;
  }
  if (!label) return null;
  return { emoji, label, category };
}

/**
 * Compose the progress message: accumulated steps, then the live reasoning
 * block underneath (when present). Single source of truth for the progress
 * bubble content while the assistant is "thinking".
 */
function buildProgressContent(
  steps: string[],
  reasoning: string,
  t: SSEHandlerContext['t']
): string {
  const stepsContent = buildAccumulatedStepsContent(steps, t);
  const reasoningBlock = buildReasoningBlock(reasoning, t);
  if (!reasoningBlock) return stepsContent;
  if (!stepsContent) return reasoningBlock;
  return `${stepsContent}\n${reasoningBlock}`;
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

  // Execution trace (Lot 2 P2-V1): a router_decision marks the turn start —
  // reset the (flip-surviving) trace accumulators and seed the router step.
  // A stable translated label is used, not the randomized analyzing message.
  context.traceStepsRef.current = [
    {
      emoji: '🧭',
      label: t('execution.steps.router_decision', { defaultValue: 'Analyzing…' }),
      category: 'system',
    },
  ];
  context.traceReasoningRef.current = '';
  const fullContent = buildProgressContent(
    executionStepsRef.current,
    context.reasoningBufRef.current,
    t
  );

  if (!progressMessageId) {
    // First progress event - create message
    setProgressMessageId(assistantMessageId);
    dispatch({
      type: 'STREAM_START',
      payload: {
        messageId: assistantMessageId,
        initialContent: fullContent,
        phase: 'progress',
      },
    });
  } else {
    // Update existing progress message
    dispatch({
      type: 'STREAM_REPLACE',
      payload: { content: fullContent, phase: 'progress' },
    });
  }
}

/**
 * Handle execution_step subtypes specific to compaction v2 (Task 3.2).
 *
 * The backend emits compaction_start / compaction_done events from the
 * compaction node (`apps/api/src/domains/agents/nodes/compaction_node.py`)
 * via LangGraph's "custom" stream_mode. They are typed as `execution_step`
 * on the wire but carry `metadata.step_type === 'compaction'` so we can
 * intercept them before the generic progress-message accumulator runs.
 *
 * The user-facing feedback is a sonner toast that morphs in place (loading →
 * success/warning) so the indicator stays visible no matter where the chat
 * scrollbar is. The reducer dispatches drive the chat-input lock via
 * `status === 'compacting'` → `isTyping`.
 *
 * Returns `true` when the chunk was handled here (no further processing
 * needed by `handleExecutionStep`).
 */
function handleCompactionStep(chunk: ChatStreamChunk, context: SSEHandlerContext): boolean {
  const metadata = chunk.metadata as Record<string, unknown> | undefined;
  if (!metadata || metadata.step_type !== 'compaction') {
    return false;
  }

  const stepLabel = metadata.step_label as string | undefined;
  if (stepLabel === 'compaction_start') {
    // Persistent loading toast — same `id` is reused on `compaction_done` so
    // sonner morphs the same toast into a success/warning rather than
    // stacking. Toasts live outside the chat scroll container, so they remain
    // visible no matter where the user is scrolled.
    // Replay (ADR-117 Lot 2): the compaction already happened — rebuild the
    // reducer state silently, no toast.
    if (!context.isReplay) {
      toast.loading(context.t('chat.compaction.in_progress'), {
        id: COMPACTION_TOAST_ID,
      });
    }
    context.dispatch({
      type: 'STREAM_COMPACTION_START',
      payload: {
        estimatedDurationSeconds: metadata.estimated_duration_seconds as number | undefined,
        strategy: metadata.strategy as string | undefined,
      },
    });
    return true;
  }
  if (stepLabel === 'compaction_done') {
    const tokensSaved = metadata.tokens_saved as number | undefined;
    const strategy = metadata.strategy as string | undefined;
    // Truncation = the LLM summary failed and we fell back to dropping older
    // messages. Surface as a warning so the user knows the recap is degraded.
    // Replay (ADR-117 Lot 2): no toast — state reconstruction only.
    if (!context.isReplay) {
      if (strategy === 'truncation') {
        toast.warning(context.t('chat.compaction.truncated'), {
          id: COMPACTION_TOAST_ID,
          duration: 6000,
        });
      } else {
        toast.success(context.t('chat.compaction.completed', { tokens: tokensSaved ?? 0 }), {
          id: COMPACTION_TOAST_ID,
          duration: 4000,
        });
      }
    }
    context.dispatch({
      type: 'STREAM_COMPACTION_DONE',
      payload: {
        tokensSaved,
        durationMs: metadata.duration_ms as number | undefined,
        strategy,
      },
    });
    return true;
  }
  // Unknown step_label for a compaction event — fall through to the generic
  // execution_step handler so we still emit *some* progress feedback.
  return false;
}

/**
 * Handle execution_step: Dynamic execution progress messages (accumulated)
 */
/**
 * Intercept connector error notices (Lot 3 P3, ADR-134).
 *
 * `step_type: "tool_error"` chunks carry a structured connector failure
 * (connector_type + action) emitted when a tool broke on connector auth.
 * They feed the reconnect/rate-limit banner — never the progress steps nor
 * the Lot 2 execution trace. Returns true when the chunk was consumed.
 */
function handleConnectorNoticeStep(chunk: ChatStreamChunk, context: SSEHandlerContext): boolean {
  const metadata = chunk.metadata as
    | { step_type?: string; connector_type?: string; action?: string; tool_name?: string }
    | undefined;
  if (metadata?.step_type !== 'tool_error') return false;

  const { connector_type: connectorType, action, tool_name: toolName } = metadata;
  if (!connectorType || (action !== 'reconnect' && action !== 'rate_limit')) {
    logger.warn(
      'chat_connector_notice_malformed',
      context.withContext({ component: 'useChat', metadata: chunk.metadata })
    );
    return true; // Consumed anyway: never fall through to the step accumulator
  }

  context.dispatch({
    type: 'CONNECTOR_NOTICE_ADD',
    payload: { notice: { connectorType, action, toolName: toolName ?? 'unknown' } },
  });
  return true;
}

/**
 * Expressive eyes: mirror the step kind so the widget can distinguish
 * "thinking" (reasoning) from "searching" (tool work) during the progress
 * phase. Pure signal recording — no dispatch, no rendering impact. Extracted
 * from handleExecutionStep to keep that hotspot under the CC ratchet.
 */
function recordEyesStepSignal(metadata: ProgressMessageMetadata | undefined): void {
  if (metadata?.step_type === 'reasoning') {
    useEyesSignalsStore.getState().recordStep('reasoning');
  } else if (metadata?.tool_name || metadata?.category === 'tool') {
    useEyesSignalsStore.getState().recordStep('tool');
  }
}

export function handleExecutionStep(chunk: ChatStreamChunk, context: SSEHandlerContext): void {
  // Intercept compaction-specific events first — they drive the chat-input
  // lock + sonner toast rather than the generic execution_step accumulator.
  if (handleCompactionStep(chunk, context)) {
    return;
  }

  // Intercept connector error notices (Lot 3 P3) — banner, not progress step.
  if (handleConnectorNoticeStep(chunk, context)) {
    return;
  }

  const {
    dispatch,
    withContext,
    t,
    progressMessageId,
    setProgressMessageId,
    assistantMessageId,
    executionStepsRef,
    emittedStepKeysRef,
    reasoningBufRef,
  } = context;

  logger.debug(
    'chat_execution_step',
    withContext({
      component: 'useChat',
      metadata: chunk.metadata,
    })
  );

  const metadata = chunk.metadata as ProgressMessageMetadata | undefined;

  recordEyesStepSignal(metadata);

  // --- Live reasoning sub-type (💭): accumulate the model's chain-of-thought ---
  // These events stream continuously during a thinking node; they are appended
  // to a dedicated buffer (NOT the step accumulator) and rendered as a muted
  // block beneath the steps. They are wiped on the first answer token, exactly
  // like the steps (see handleToken / handleContentReplacement).
  if (metadata?.step_type === 'reasoning') {
    if (metadata.delta) {
      reasoningBufRef.current += metadata.delta;
      // Trace (Lot 2): keep a flip-surviving copy of the reasoning.
      context.traceReasoningRef.current += metadata.delta;
    }
  } else {
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

    // Trace (Lot 2): accumulate the structured step in parallel — this ref is
    // NOT wiped at the answer flip, so it survives to be attached at `done`.
    const traceStep = buildTraceStep(metadata, t);
    if (traceStep) context.traceStepsRef.current.push(traceStep);
  }

  const fullContent = buildProgressContent(executionStepsRef.current, reasoningBufRef.current, t);

  if (progressMessageId) {
    dispatch({
      type: 'STREAM_REPLACE',
      payload: { content: fullContent, phase: 'progress' },
    });
  } else {
    // Edge case: execution_step arrived before router_decision
    setProgressMessageId(assistantMessageId);
    dispatch({
      type: 'STREAM_START',
      payload: {
        messageId: assistantMessageId,
        initialContent: fullContent,
        phase: 'progress',
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
    // Clear accumulated execution steps + live reasoning — real content is arriving
    executionStepsRef.current = [];
    context.emittedStepKeysRef.current = new Set();
    context.reasoningBufRef.current = '';
    // Progress message exists → replace with first token
    dispatch({
      type: 'STREAM_REPLACE',
      payload: { content: chunk.content, phase: 'answer' },
    });
    setNormalStreamInitialized(true);
    setProgressMessageId(null); // Progress phase complete
  } else if (!normalStreamInitialized) {
    // No progress message (backwards compatible) → create new message
    dispatch({
      type: 'STREAM_START',
      payload: { messageId: assistantMessageId, phase: 'answer' },
    });
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
    // Clear accumulated execution steps + live reasoning — real content is arriving
    executionStepsRef.current = [];
    context.emittedStepKeysRef.current = new Set();
    context.reasoningBufRef.current = '';
    dispatch({
      type: 'STREAM_START',
      payload: { messageId: assistantMessageId, phase: 'answer' },
    });
    setNormalStreamInitialized(true);
    if (progressMessageId) {
      setProgressMessageId(null);
    }
  }

  dispatch({
    type: 'STREAM_REPLACE',
    payload: { content: chunk.content as string, phase: 'answer' },
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

  // Expressivity (ADR-253): the register the answering model declared for THIS
  // answer. Parked BEFORE STREAM_DONE for the same reason the trace is: the
  // dispatch below flips the status to idle, and that transition is what makes
  // the avatar react.
  useEyesSignalsStore.getState().setTone(parseToneAnnotation(metadata?.expressivity));

  // Execution trace (Lot 2 P2-V1): attach the flip-surviving backstage record
  // to the completed message BEFORE STREAM_DONE flips status to idle. Skipped
  // when nothing was captured (e.g. a pure-conversation reply with no steps).
  attachExecutionTrace(context, assistantMessageId, metadata?.duration_ms);

  dispatch({
    type: 'STREAM_DONE',
    payload: {
      messageId: assistantMessageId,
      metadata,
    },
  });
}

/**
 * Attach the captured execution trace to a message (Lot 2 P2-V1).
 *
 * No-op when no step was captured — a trace of nothing adds a useless empty
 * disclosure. The step/reasoning refs survive the answer flip on purpose, so
 * at `done` they still hold the whole turn.
 */
function attachExecutionTrace(
  context: SSEHandlerContext,
  messageId: string,
  durationMs: number | undefined
): void {
  const steps = context.traceStepsRef.current;
  if (steps.length === 0) return;

  const trace: ExecutionTrace = {
    steps: [...steps],
    reasoning: context.traceReasoningRef.current,
    ...(typeof durationMs === 'number' ? { durationMs } : {}),
  };
  context.dispatch({ type: 'TRACE_ATTACH', payload: { messageId, trace } });
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

  // Approval card (Lot 1 P1-V1): build the card state from the wire payload.
  // Last-wins by design (a fresh interrupt replaces any previous card) and
  // replay-safe: an interrupt run's backlog ends at the interrupt, so the
  // replayed metadata chunk legitimately re-arms the card. Out-of-scope
  // kinds (clarification…) normalize to null — text-only flow, no card.
  const normalized = normalizeHitlPayload(chunk.metadata);
  if (normalized) {
    dispatch({ type: 'HITL_AWAITING', payload: { payload: normalized } });
  }

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
      payload: { content: hitlMessage, phase: 'progress' },
    });
  } else {
    // Fallback: create message if router/planner didn't fire (edge case)
    setProgressMessageId(messageId);
    dispatch({
      type: 'STREAM_START',
      payload: {
        messageId: messageId,
        initialContent: hitlMessage,
        phase: 'progress',
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
    dispatch({ type: 'STREAM_REPLACE', payload: { content: token, phase: 'answer' } });
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
  // Capture BEFORE the buffer is deleted below — reading it after delete
  // made fallback_used always true in the completion log.
  const fallbackUsed = !finalQuestion;

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
      fallback_used: fallbackUsed,
    })
  );
}

/**
 * Handle hitl_streaming_fallback: HITL question streaming degraded.
 *
 * Awareness-only event: the backend emits it when the LLM stream generating
 * the HITL question fails and it falls back to a template question. The
 * regular hitl_question_token chunks that follow carry that fallback text,
 * so the UX needs no action here — but the degradation must be visible in
 * the frontend logs (it went unnoticed for months as an unknown event type).
 */
export function handleHitlStreamingFallback(
  chunk: ChatStreamChunk,
  context: SSEHandlerContext
): void {
  const { withContext } = context;
  const metadata = chunk.metadata as Record<string, unknown> | undefined;

  logger.warn(
    'chat_hitl_streaming_fallback',
    withContext({
      component: 'useChat',
      message_id: metadata?.message_id,
      error_type: metadata?.error_type,
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
  // phase 'answer': the HITL question is content, not execution steps — the
  // interrupt-metadata handler may have left the stream in the progress phase.
  dispatch({ type: 'STREAM_START', payload: { messageId: legacyMessageId, phase: 'answer' } });
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

  // Replay (ADR-117 Lot 2): stale audio must never play. The server already
  // drops voice chunks from the replayed backlog — this is belt-and-braces.
  if (context.isReplay) {
    return;
  }

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

  // Usage limit exceeded — show specific toast (from Layer 1/2 enforcement).
  // Replay (ADR-117 Lot 2): the toast already fired when it happened live.
  if (errorCode === 'usage_limit_exceeded' && !context.isReplay) {
    toast.error(chunk.content || 'Usage limit exceeded');
  }

  // The INSTANCE exhausted its daily spend ceiling: nothing is wrong with
  // this account and contacting an administrator changes nothing today, so
  // the personal-quota sentence would be wrong twice. The backend content is
  // technical and English-only — the visitor reads the translated key.
  if (errorCode === 'instance_budget_exhausted' && !context.isReplay) {
    toast.error(context.t('errors.chat.instance_budget_exhausted'));
  }

  // Approval card (Lot 1 P1-V1): the one-click decision no longer matches
  // the pending interrupt (expired / answered / superseded) — flip the card
  // to its terminal 'expired' state BEFORE the generic STREAM_ERROR below,
  // whose submitting→awaiting retry branch must not re-arm dead buttons.
  if (errorCode === 'hitl_decision_stale') {
    dispatch({ type: 'HITL_EXPIRED' });
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

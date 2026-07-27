import { useReducer, useCallback, useEffect, useRef, Dispatch } from 'react';
import {
  Message,
  MessageAttachmentMeta,
  ChatStreamChunk,
  RegistryItem,
  BrowserContext,
  DebugMetrics,
  BrowserScreenshotData,
} from '@/types/chat';
import {
  ConversationTotals,
  ChatAction,
  ChatState,
  DebugMetricsEntry,
  ContextUsage,
  StreamPhase,
} from '@/types/chat-state';
import { normalizeHitlPayload } from '@/lib/hitl-payload';
import type { HitlDecisionWire } from '@/types/hitl';
import type { ExecutionTraceStep } from '@/types/execution-trace';
import {
  chatReducer,
  createInitialState,
  persistDebugMetricsHistory,
} from '@/reducers/chat-reducer';
import { validateReducerAction } from '@/reducers/chat-reducer-errors';
import {
  cancelActiveRun,
  chatSSEClient,
  ChatStreamError,
  fetchActiveRun,
  fetchPendingHitl,
} from '@/lib/api/chat';
import { useAuth } from '@/hooks/useAuth';
import { useGeolocation } from '@/hooks/useGeolocation';
import { useLiaGender } from '@/hooks/useLiaGender';
import { useVoicePlayback } from '@/hooks/useVoicePlayback';
import { useAPIHealth } from '@/hooks/useAPIHealth';
import { logger } from '@/lib/logger';
import { useLoggingContext } from '@/lib/logging-context';
import { useTranslation } from 'react-i18next';
import { generateUUID } from '@/lib/utils';
import { messageRequiresGeolocation } from '@/lib/location-detection';
import { toast } from 'sonner';
import {
  flushTokenBatching,
  processSSEChunk,
  resetTokenBatching,
  SSEHandlerContext,
} from '@/lib/sse-handlers';
import { DEBUG_PANEL_TOTAL_WIDTH_PX } from '@/lib/constants';

/**
 * Custom hook for managing chat state with SSE streaming.
 *
 * Refactored (Phase 2.2):
 * - Uses useReducer for predictable state management
 * - Finite state machine for chat lifecycle
 * - Pure reducer functions (easy to test)
 * - Centralized state transitions
 *
 * State Machine:
 *   idle → sending → streaming → idle
 *          ↓         ↓
 *        error ←----
 */

export interface UseChatReturn {
  messages: Message[];
  isTyping: boolean;
  /** Id of the assistant message currently receiving stream updates (null when idle). */
  activeStreamId: string | null;
  /** 'progress' while the active message shows execution steps, 'answer' on real tokens. */
  streamPhase: StreamPhase;
  isConnected: boolean;
  apiAvailable: boolean;
  conversationTotals: ConversationTotals;
  sendMessage: (
    content: string,
    attachmentIds?: string[],
    attachmentsMeta?: MessageAttachmentMeta[],
    /**
     * Optional remote-STT cost metadata. Forwarded to the backend so the
     * resulting user-bubble row carries the precise cost. NULL/absent for
     * text-only sends or local-Sherpa transcriptions.
     */
    sttMeta?: import('@/lib/voice-input-service').VoiceTranscriptionMeta & {
      stt_audio_duration_seconds?: number | null;
    },
    hitlDecision?: HitlDecisionWire
  ) => Promise<void>;
  clearMessages: () => void;
  setMessages: (messages: Message[]) => void;
  appendMessage: (message: Message) => void;
  isLoadingHistory: boolean;
  // LARS: Registry for rich rendering
  registry: Record<string, RegistryItem>;
  getRegistryItem: (id: string) => RegistryItem | undefined;
  // Debug Panel: Scoring metrics for threshold tuning (current request only)
  currentDebugMetrics: DebugMetrics | null;
  // Debug Panel: Cumulative history of all request metrics (collapsible display)
  debugMetricsHistory: DebugMetricsEntry[];
  // Browser Screenshots: Current overlay data
  browserScreenshot: BrowserScreenshotData | null;
  clearBrowserScreenshot: () => void;
  // Context-usage pill (2026-05): current conversation token footprint vs the
  // dynamic compaction threshold. `null` until the first turn completes. The
  // compaction in-flight state itself stays in the reducer (drives
  // `status === 'compacting'` → input lock) but no consumer needs to read it
  // — the sonner toast is fully managed by `handleCompactionStep`.
  contextUsage: ContextUsage | null;
  /**
   * Hydrate the context-usage pill from the server-side totals payload.
   * No-op on missing or invalid values.
   */
  hydrateContextUsage: (
    tokens: number | null | undefined,
    threshold: number | null | undefined
  ) => void;
  /** HITL approval card state (Lot 1 P1-V1). */
  hitl: ChatState['hitl'];
  /**
   * Rehydrate the approval card after a page reload: fetches the pending
   * interrupt (GET /agents/hitl/pending) and re-arms the card when one is
   * pending. Safe no-op on null/failure — progressive enhancement only.
   */
  hydratePendingHitl: () => Promise<void>;
  /**
   * One-click HITL approval (Lot 1 P1-V1): locks the card (submitting),
   * then sends the localized button label as the message with the
   * structured decision attached. Wire action ids pass through verbatim
   * (the backend canonicalizes aliases).
   */
  submitHitlDecision: (
    wireAction: string,
    labelText: string,
    modificationInstructions?: string
  ) => Promise<void>;
  /** Connector error banners accumulated for the current turn (Lot 3 P3). */
  connectorNotices: ChatState['connectorNotices'];
  /** Dismiss one connector banner by its (connector, action) identity. */
  dismissConnectorNotice: (connectorType: string, action: 'reconnect' | 'rate_limit') => void;
  /** ADR-117 Lot 2: reattach to an in-flight background run (replay + live). */
  resumeActiveRun: (streamId: string) => Promise<void>;
  /**
   * ADR-117 Lot 2: check for an active background run and silently resume
   * it. Returns true when a resume was started (does not await the stream).
   */
  checkAndResumeActiveRun: () => Promise<boolean>;
  /**
   * ADR-117 Lot 3 (stop button): cancel the in-flight generation. Flag ON,
   * the server cancels the detached run (the partial answer is kept and
   * flagged); the synthesized `done` chunk then closes the stream normally.
   * Flag OFF (or no active run), falls back to the legacy local abort.
   */
  stopGeneration: () => Promise<void>;
}

/**
 * Build the chat-stream request body (pure, hook-free).
 *
 * Optional blocks: attachments, remote-STT cost metadata (persisted on the
 * user ConversationMessage row), and the one-click HITL decision (Lot 1
 * P1-V1) — the structured decision rides the normal send, with the localized
 * button label as message content (user bubble + graceful NL fallback on
 * older backends).
 */
function buildChatRequest(args: {
  content: string;
  userId: string;
  sessionId: string;
  browserContext: BrowserContext;
  attachmentIds?: string[];
  sttMeta?: import('@/lib/voice-input-service').VoiceTranscriptionMeta & {
    stt_audio_duration_seconds?: number | null;
  };
  hitlDecision?: HitlDecisionWire;
}) {
  const { content, userId, sessionId, browserContext, attachmentIds, sttMeta, hitlDecision } = args;
  return {
    message: content,
    user_id: userId,
    session_id: sessionId,
    context: browserContext,
    ...(attachmentIds && attachmentIds.length > 0 ? { attachment_ids: attachmentIds } : {}),
    ...(sttMeta?.stt_provider
      ? {
          stt_provider: sttMeta.stt_provider,
          stt_audio_duration_seconds: sttMeta.stt_audio_duration_seconds ?? null,
          stt_cost_usd: sttMeta.stt_cost_usd ?? null,
          stt_cost_eur: sttMeta.stt_cost_eur ?? null,
        }
      : {}),
    ...(hitlDecision ? { hitl_decision: hitlDecision } : {}),
  };
}

export const useChat = ({
  debugPanelVisible = false,
}: { debugPanelVisible?: boolean } = {}): UseChatReturn => {
  const { user } = useAuth();
  const { withContext } = useLoggingContext();
  const { t, i18n } = useTranslation();

  // Geolocation for location-aware features (weather, places)
  // Includes enable() to trigger permission request when location is needed
  const {
    coordinates: geolocation,
    isEnabled: geolocationEnabled,
    enable: enableGeolocation,
    permission: geolocationPermission,
  } = useGeolocation();

  // Voice playback for TTS audio streaming
  const { handleVoiceChunk, stopPlayback, warmupAudio, recordUserInteraction } = useVoicePlayback();

  // LIA gender preference (for TTS voice selection)
  const { isMale: liaIsMale } = useLiaGender();

  // Get current language for location detection (from i18n instance, not translation key)
  const currentLanguage = (i18n.language || 'fr').split('-')[0];

  // State management with useReducer (replaces multiple useState calls)
  const [state, baseDispatch] = useReducer(chatReducer, createInitialState());

  // Persist debug metrics history to sessionStorage so it survives page navigation
  useEffect(() => {
    persistDebugMetricsHistory(state.debugMetricsHistory);
  }, [state.debugMetricsHistory]);

  // Latest-state ref for the dev-only dispatch validation below.
  // The wrapper used to depend on [state] (recreated on every token) while
  // downstream callbacks exclude `dispatch` from their deps ("stable from
  // useReducer") — so their captured wrapper validated against a STALE state.
  // The ref is synced post-commit (render-phase ref writes are forbidden),
  // which keeps the dispatch wrapper genuinely stable AND validates against
  // current state: dispatches come from SSE/browser events, which fire after
  // the commit that updated `state`, never mid-render.
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  /**
   * Validated dispatch wrapper - logs errors before passing to pure reducer.
   * This maintains reducer purity while enabling error detection.
   */
  const dispatch: Dispatch<ChatAction> = useCallback((action: ChatAction) => {
    // Validate action against current state (development only)
    if (process.env.NODE_ENV === 'development') {
      const errors = validateReducerAction(stateRef.current, action);
      errors.forEach(validationError => {
        const logContext = {
          errorType: validationError.type,
          action: validationError.action,
          severity: validationError.severity,
          ...validationError.context,
        };

        // Log with appropriate severity level
        switch (validationError.severity) {
          case 'error':
            logger.error('reducer_validation_error', undefined, logContext);
            break;
          case 'warning':
            logger.warn('reducer_validation_warning', logContext);
            break;
          case 'debug':
            logger.debug('reducer_validation_debug', logContext);
            break;
        }
      });
    }

    // Pass to pure reducer
    baseDispatch(action);
  }, []);

  /**
   * Resolve a stream error to a user-facing, localized message.
   *
   * ChatStreamError carries the i18n key of the typed HTTP/network failure
   * (session expired, usage limit, …); any other error is wrapped in the
   * generic connection-error template. The SSE_ERROR reducer renders the
   * result verbatim — localization happens here, where t() is available.
   */
  const resolveStreamErrorMessage = useCallback(
    (error: Error): string => {
      if (error instanceof ChatStreamError) {
        return t(error.i18nKey, { ...error.i18nParams, defaultValue: error.message });
      }
      return t('errors.chat.connection_error', { message: error.message });
    },
    [t]
  );

  // HITL streaming buffer (stores partial questions during progressive rendering)
  const hitlQuestionBuffer = useRef<Map<string, string>>(new Map());

  // Accumulated execution steps for progressive display (cleared on first token)
  const executionStepsRef = useRef<string[]>([]);
  // Set of i18n_keys already emitted — deduplication between router/planner and execution_step
  const emittedStepKeysRef = useRef<Set<string>>(new Set());
  // Live reasoning (💭) accumulated text — cleared on first answer token
  const reasoningBufRef = useRef<string>('');
  // Execution trace accumulators (Lot 2 P2-V1): parallel to the ephemeral
  // refs above but NOT wiped at the answer flip — they survive to `done`
  // where the backstage record is attached to the message.
  const traceStepsRef = useRef<ExecutionTraceStep[]>([]);
  const traceReasoningRef = useRef<string>('');

  // API health monitoring - syncs with reducer state via callback
  useAPIHealth({
    user,
    onStatusChange: useCallback(
      (available: boolean) => {
        dispatch({ type: 'SET_API_AVAILABLE', payload: { available } });
      },
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [] // dispatch excluded: stable from useReducer (React guarantees identity stability)
    ),
  });

  /**
   * Reattach to an in-flight background run (ADR-117 Lot 2).
   *
   * Replays the run's backlog through the exact same handler pipeline as a
   * live stream (the reducer rebuilds the in-progress assistant bubble),
   * with `isReplay: true` suppressing out-of-reducer side effects (toasts,
   * voice) until the server's `: replay-end` boundary, then follows the
   * live tail to completion. Reuses the existing FSM lifecycle:
   * SSE_CONNECTING → (replayed chunks drive STREAM_START/streaming) → done.
   */
  const resumeActiveRun = useCallback(
    async (streamId: string) => {
      // Never stack two subscriptions on the singleton client
      chatSSEClient.cancel();
      stopPlayback();

      const assistantMessageId = generateUUID();
      let progressMessageId: string | null = null;
      let normalStreamInitialized = false;
      let replayDone = false;

      executionStepsRef.current = [];
      emittedStepKeysRef.current = new Set();
      reasoningBufRef.current = '';
      resetTokenBatching();

      logger.info('chat_resume_active_run', withContext({ component: 'useChat' }));
      dispatch({ type: 'SSE_CONNECTING' });

      try {
        await chatSSEClient.reattachStream(
          streamId,
          (chunk: ChatStreamChunk) => {
            const handlerContext: SSEHandlerContext = {
              dispatch,
              t,
              withContext,
              handleVoiceChunk,
              hitlQuestionBuffer,
              executionStepsRef,
              emittedStepKeysRef,
              reasoningBufRef,
              traceStepsRef,
              traceReasoningRef,
              assistantMessageId,
              progressMessageId,
              setProgressMessageId: (id: string | null) => {
                progressMessageId = id;
              },
              normalStreamInitialized,
              setNormalStreamInitialized: (v: boolean) => {
                normalStreamInitialized = v;
              },
              isReplay: !replayDone,
            };
            processSSEChunk(chunk, handlerContext);
          },
          (error: Error) => {
            flushTokenBatching();
            if (error instanceof ChatStreamError && error.name === 'RunGoneError') {
              // The run finished between the active-run check and this call —
              // the history reload owns that content now. Not an error state.
              logger.info('chat_resume_run_gone', withContext({ component: 'useChat' }));
              dispatch({ type: 'SSE_DISCONNECTED' });
              return;
            }
            dispatch({
              type: 'SSE_ERROR',
              payload: { error: resolveStreamErrorMessage(error) },
            });
          },
          () => {
            dispatch({ type: 'SSE_DISCONNECTED' });
          },
          () => {
            replayDone = true;
          }
        );
      } catch (error) {
        dispatch({
          type: 'SSE_ERROR',
          payload: { error: resolveStreamErrorMessage(error as Error) },
        });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, withContext, stopPlayback, handleVoiceChunk, resolveStreamErrorMessage] // dispatch excluded: stable from useReducer
  );

  /**
   * Check for an in-flight background run and silently reattach to it
   * (product decision 2026-07: automatic resume, no banner). Returns true
   * when a resume was started — the stream keeps flowing in the background,
   * this does NOT await its completion.
   */
  const checkAndResumeActiveRun = useCallback(async (): Promise<boolean> => {
    const status = await fetchActiveRun();
    if (!status.active || !status.stream_id) {
      return false;
    }
    void resumeActiveRun(status.stream_id);
    return true;
  }, [resumeActiveRun]);

  /**
   * Stop the in-flight generation (ADR-117 Lot 3).
   *
   * Server-side cancellation first: the detached producer archives the
   * partial answer (flagged `interrupted`) and synthesizes a `done` chunk
   * with `metadata.cancelled` — our open subscription receives it and the
   * FSM closes normally (the partial bubble stays, badged). When no
   * detached run exists (flag OFF / legacy path), falls back to the local
   * abort, which kills the inline generation exactly as before ADR-117.
   */
  const stopGeneration = useCallback(async () => {
    const { cancelled } = await cancelActiveRun();
    if (cancelled) {
      // The stream stays open: the synthesized done arrives within
      // ~BACKGROUND_RUNS_CANCEL_POLL_SECONDS and finalizes the bubble.
      logger.info('chat_stop_requested', withContext({ component: 'useChat' }));
      return;
    }
    // Legacy fallback: no detached run to cancel — abort locally.
    logger.info('chat_stop_local_abort', withContext({ component: 'useChat' }));
    chatSSEClient.cancel();
    stopPlayback();
    flushTokenBatching();
    dispatch({ type: 'SSE_DISCONNECTED' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [withContext, stopPlayback]); // dispatch excluded: stable from useReducer

  /**
   * Send a chat message and handle SSE streaming response.
   */
  const sendMessage = useCallback(
    async (
      content: string,
      attachmentIds?: string[],
      attachmentsMeta?: MessageAttachmentMeta[],
      sttMeta?: import('@/lib/voice-input-service').VoiceTranscriptionMeta & {
        stt_audio_duration_seconds?: number | null;
      },
      hitlDecision?: HitlDecisionWire
    ) => {
      // ✅ CRITICAL: Cancel any pending stream before starting new one
      // Prevents double token counting and ensures clean state
      chatSSEClient.cancel();

      // Stop any playing voice audio when sending a new message
      stopPlayback();

      // ✅ iOS FIX: Record user interaction and warmup AudioContext on user gesture
      // iOS requires AudioContext.resume() to be called directly in a user event handler.
      // Recording the interaction timestamp helps iOS resume suspended contexts later.
      // warmupAudio() plays a silent buffer to "unlock" iOS audio (more reliable than just initialize).
      // Calling it here (in sendMessage triggered by click/Enter) satisfies iOS autoplay policy.
      recordUserInteraction();
      warmupAudio().catch(() => {
        // Silently ignore - audio will try to warmup on first chunk if needed
      });

      if (!user) {
        logger.error(
          'send_message_no_user',
          undefined,
          withContext({
            component: 'useChat',
          })
        );
        return;
      }

      // ========================================================================
      // GEOLOCATION INTERCEPTION: Request permission if message needs location
      // ========================================================================
      // Detect location phrases ("dans le coin", "nearby", "chez moi", etc.)
      // and trigger browser geolocation request if coordinates not available
      const needsGeolocation = messageRequiresGeolocation(content, currentLanguage);

      if (needsGeolocation && !geolocation && geolocationPermission !== 'denied') {
        // Trigger browser geolocation permission request
        toast.info(t('chat.geolocation.prompt_title'), {
          description: t('chat.geolocation.prompt_description'),
          duration: 5000,
        });

        // Enable geolocation (triggers browser permission request)
        // Don't await - let the message continue while permission is requested
        // User's next message will have coordinates if they accept
        enableGeolocation().then(result => {
          if (result) {
            toast.success(t('chat.geolocation.enabled_success'));
          }
        });
      }

      // Create user message (include attachment metadata for immediate thumbnail display)
      const userMessage: Message = {
        id: generateUUID(),
        content,
        role: 'user',
        timestamp: new Date(),
        avatar: user.picture_url || undefined,
        ...(attachmentsMeta && attachmentsMeta.length > 0
          ? { metadata: { attachments: attachmentsMeta } }
          : {}),
        // Surface remote-STT cost on the optimistic user bubble immediately
        // so the badge appears at send time (before backend echoes the row).
        ...(sttMeta?.stt_provider
          ? {
              source: 'voice' as const,
              sttProvider: sttMeta.stt_provider ?? null,
              sttAudioDurationSeconds: sttMeta.stt_audio_duration_seconds ?? null,
              sttCostEur: sttMeta.stt_cost_eur ?? null,
              audioDurationSeconds: sttMeta.stt_audio_duration_seconds ?? undefined,
            }
          : {}),
      };

      // Dispatch user message (state: idle → sending)
      // Note: Removed console.log to avoid logging user message content (PII)
      dispatch({ type: 'SEND_MESSAGE', payload: { message: userMessage } });

      // Generate message ID for assistant response
      const assistantMessageId = generateUUID();

      // Don't create message immediately - wait for first content
      // Message will be created when hitl_interrupt_metadata or first token arrives
      // Note: Removed console.log - use structured logger.debug instead for non-PII metadata

      // Track if we've initialized streaming for this message (prevents multiple STREAM_START dispatches)
      let normalStreamInitialized = false;

      // Track progress message lifecycle (ephemeral messages: router → planner → execution_step → HITL)
      let progressMessageId: string | null = null;

      // Reset accumulated execution steps + live reasoning for this new message
      executionStepsRef.current = [];
      emittedStepKeysRef.current = new Set();
      reasoningBufRef.current = '';
      // Trace accumulators reset per turn (Lot 2): a router_decision re-seeds
      // them, this guards the edge where the first event is not a router.
      traceStepsRef.current = [];
      traceReasoningRef.current = '';

      // Prepare SSE request
      // Session management: Using user.id as session identifier
      // Sessions are persisted in backend Redis store via HTTP-only cookie
      const sessionId = `session_${user.id}`;

      // Build browser context with geolocation and LIA gender preference
      // This is sent automatically with each message for location-aware features and voice selection
      const browserContext: BrowserContext = {
        // Geolocation (if enabled and available)
        geolocation:
          geolocationEnabled && geolocation
            ? {
                lat: geolocation.lat,
                lon: geolocation.lon,
                accuracy: geolocation.accuracy,
                timestamp: geolocation.timestamp,
              }
            : null,
        // LIA gender preference (for TTS voice selection)
        lia_gender: liaIsMale ? 'male' : 'female',
        // Viewport width for responsive HTML rendering
        // When debug panel is visible, subtract its width to get actual content area width
        viewport_width:
          typeof window !== 'undefined'
            ? window.innerWidth - (debugPanelVisible ? DEBUG_PANEL_TOTAL_WIDTH_PX : 0)
            : null,
      };

      const request = buildChatRequest({
        content,
        userId: user.id,
        sessionId,
        browserContext,
        attachmentIds,
        sttMeta,
        hitlDecision,
      });

      try {
        // Drop any tokens still buffered by a previous (cancelled) stream —
        // a late animation-frame flush must never leak into this message.
        resetTokenBatching();

        await chatSSEClient.streamChat(
          request,
          // onChunk: Handle each SSE chunk via extracted handlers
          (chunk: ChatStreamChunk) => {
            // Build handler context with mutable state access
            const handlerContext: SSEHandlerContext = {
              dispatch,
              t,
              withContext,
              handleVoiceChunk,
              hitlQuestionBuffer,
              executionStepsRef,
              emittedStepKeysRef,
              reasoningBufRef,
              traceStepsRef,
              traceReasoningRef,
              assistantMessageId,
              progressMessageId,
              setProgressMessageId: (id: string | null) => {
                progressMessageId = id;
              },
              normalStreamInitialized,
              setNormalStreamInitialized: (v: boolean) => {
                normalStreamInitialized = v;
              },
              isReplay: false,
            };

            // Delegate to extracted SSE handlers (see lib/sse-handlers/)
            processSSEChunk(chunk, handlerContext);
          },
          // onError: Handle SSE connection errors
          (error: Error) => {
            // ADR-117 Lot 2: HTTP 409 — another run is already streaming for
            // this conversation (multi-tab / return-mid-run race). Reattach
            // to it instead of erroring. The optimistic user bubble stays
            // visible but unsent; the next history reload reconciles it.
            if (
              error instanceof ChatStreamError &&
              error.name === 'RunInProgressError' &&
              error.activeStreamId
            ) {
              toast.info(t('chat.resume.in_progress'));
              void resumeActiveRun(error.activeStreamId);
              return;
            }

            // The stall watchdog fired: the socket went silent (a frozen
            // mobile tab, typically) but the run itself carries on
            // server-side. Leave `streaming` FIRST — `isTyping` is what makes
            // the visibility handler skip its own resume — then ask
            // /runs/active who to rejoin. Falling through also renders the
            // localized message, so a run that really is gone says so instead
            // of leaving an empty bubble.
            if (error instanceof ChatStreamError && error.name === 'StreamStalledError') {
              logger.warn(
                'chat_sse_stalled_attempting_resume',
                withContext({ component: 'useChat' })
              );
              flushTokenBatching();
              dispatch({
                type: 'SSE_ERROR',
                payload: { error: resolveStreamErrorMessage(error) },
              });
              void checkAndResumeActiveRun();
              return;
            }

            logger.error(
              'chat_sse_error',
              error,
              withContext({
                component: 'useChat',
              })
            );

            // Show tokens received before the error (pre-batching behavior)
            // and prevent a late animation-frame flush after SSE_ERROR.
            flushTokenBatching();

            // Transition to error state (message localized here — the pure
            // reducer renders it verbatim)
            dispatch({
              type: 'SSE_ERROR',
              payload: { error: resolveStreamErrorMessage(error) },
            });
          },
          // onDone: SSE stream completed
          () => {
            logger.info(
              'chat_sse_stream_completed',
              withContext({
                component: 'useChat',
              })
            );

            // Ensure we're in idle state
            dispatch({ type: 'SSE_DISCONNECTED' });
          }
        );
      } catch (error) {
        logger.error(
          'send_message_error',
          error as Error,
          withContext({
            component: 'useChat',
          })
        );

        // Transition to error state (message localized here)
        dispatch({
          type: 'SSE_ERROR',
          payload: { error: resolveStreamErrorMessage(error as Error) },
        });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      user,
      withContext,
      geolocation,
      geolocationEnabled,
      currentLanguage,
      enableGeolocation,
      geolocationPermission,
      t,
      resolveStreamErrorMessage,
      resumeActiveRun,
      checkAndResumeActiveRun,
      stopPlayback,
      handleVoiceChunk,
      warmupAudio,
      recordUserInteraction,
      debugPanelVisible,
    ] // dispatch excluded: stable from useReducer
  );

  /**
   * Clear all messages and reset conversation state.
   */
  const clearMessages = useCallback(() => {
    dispatch({ type: 'CLEAR_MESSAGES' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // dispatch excluded: stable from useReducer

  // ========================================================================
  // Voice interruption handlers + iOS AudioContext resume
  // ========================================================================
  // Stop voice playback on user interaction (double-tap on mobile, click on desktop)
  // Also record interactions to help iOS resume suspended AudioContext
  useEffect(() => {
    const handleInterrupt = () => {
      // ✅ iOS FIX: Record every click as user interaction
      // This helps iOS resume AudioContext on subsequent audio playback
      recordUserInteraction();
      stopPlayback();
    };

    // Desktop: stop on click
    document.addEventListener('click', handleInterrupt, { capture: true });

    // Mobile: stop on double-tap only (not single tap)
    // This allows users to scroll and interact without accidentally stopping voice
    let lastTapTime = 0;
    const DOUBLE_TAP_DELAY = 300; // ms

    const handleDoubleTap = () => {
      // ✅ iOS FIX: Record every touch as user interaction
      recordUserInteraction();

      const now = Date.now();
      if (now - lastTapTime < DOUBLE_TAP_DELAY) {
        // Double tap detected
        stopPlayback();
        lastTapTime = 0; // Reset to prevent triple-tap
      } else {
        lastTapTime = now;
      }
    };
    document.addEventListener('touchstart', handleDoubleTap, { capture: true });

    // Stop if page becomes hidden (tab switch, minimize, etc.)
    const handleVisibility = () => {
      if (document.hidden) stopPlayback();
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      document.removeEventListener('click', handleInterrupt, { capture: true });
      document.removeEventListener('touchstart', handleDoubleTap, { capture: true });
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [stopPlayback, recordUserInteraction]);

  /**
   * Set messages (for loading conversation history).
   */
  /**
   * Cleanup SSE connection on unmount.
   */
  useEffect(() => {
    return () => {
      chatSSEClient.cancel();
    };
  }, []);

  const setMessages = useCallback(
    (messages: Message[]) => {
      // DEFENSIVE: Validate that messages is actually an array
      if (!Array.isArray(messages)) {
        logger.error(
          'setMessages_invalid_type',
          new Error('messages is not an array'),
          withContext({
            component: 'useChat',
            receivedType: typeof messages,
            receivedValue: messages,
          })
        );
        // Don't dispatch - keep current state
        return;
      }

      dispatch({ type: 'SET_MESSAGES', payload: { messages } });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [withContext] // dispatch excluded: stable from useReducer
  );

  /**
   * Append a single message without replacing the entire messages array.
   * Used for real-time notifications (reminders, etc.) to avoid disrupting streaming.
   * Deduplication is handled by the reducer.
   */
  const appendMessage = useCallback(
    (message: Message) => {
      dispatch({ type: 'APPEND_MESSAGE', payload: { message } });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [] // dispatch excluded: stable from useReducer (React guarantees identity stability)
  );

  /**
   * LARS: Get a specific item from the registry by ID.
   * Used by DSL parser to resolve <View id="..."/> and <Ref id="..."/> tags.
   *
   * @param id - Registry item ID (e.g., "contact_abc123")
   * @returns RegistryItem or undefined if not found
   */
  const getRegistryItem = useCallback(
    (id: string): RegistryItem | undefined => {
      return state.registry[id];
    },
    [state.registry]
  );

  /**
   * Clear the browser screenshot overlay.
   * Called when user dismisses the overlay or auto-dismiss timer fires.
   */
  const clearBrowserScreenshot = useCallback(() => {
    dispatch({ type: 'BROWSER_SCREENSHOT_CLEAR' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // dispatch excluded: stable from useReducer

  /**
   * Hydrate the context-usage pill from server totals on page load.
   * No-op when threshold is zero/negative (defensive) or values missing.
   * Called by the chat page after /conversations/me/totals returns.
   */
  const hydrateContextUsage = useCallback(
    (tokens: number | null | undefined, threshold: number | null | undefined) => {
      if (typeof tokens !== 'number' || typeof threshold !== 'number' || threshold <= 0) {
        return;
      }
      dispatch({ type: 'CONTEXT_USAGE_HYDRATE', payload: { tokens, threshold } });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [] // dispatch excluded: stable from useReducer
  );

  /**
   * HITL card rehydration (Lot 1 P1-V1) — called by the chat page at mount,
   * alongside history loading. The wire payload is normalized here; out-of-
   * scope kinds (clarification…) yield null and no card appears.
   */
  const hydratePendingHitl = useCallback(async () => {
    const pending = await fetchPendingHitl();
    const normalized = normalizeHitlPayload(pending);
    if (normalized) {
      dispatch({ type: 'HITL_AWAITING', payload: { payload: normalized } });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // dispatch excluded: stable from useReducer

  /** Wire→canonical action mapping (mirror of the backend alias table). */
  const canonicalHitlAction = (wireAction: string): 'confirm' | 'cancel' =>
    ['cancel', 'reject'].includes(wireAction) ? 'cancel' : 'confirm';

  const submitHitlDecision = useCallback(
    async (wireAction: string, labelText: string, modificationInstructions?: string) => {
      const { status, payload } = stateRef.current.hitl;
      if (status !== 'awaiting' || !payload?.messageId) {
        return; // Defensive: no live card, or unidentifiable interrupt
      }
      // Lock the buttons BEFORE the send: SEND_MESSAGE keeps a 'submitting'
      // card untouched (the via_text rule only fires on 'awaiting').
      dispatch({ type: 'HITL_SUBMITTING', payload: { action: canonicalHitlAction(wireAction) } });
      await sendMessage(labelText, undefined, undefined, undefined, {
        message_id: payload.messageId,
        action: wireAction,
        ...(modificationInstructions
          ? { modification_instructions: modificationInstructions }
          : {}),
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sendMessage] // dispatch/stateRef stable
  );

  // Connector error notices (Lot 3 P3): dismiss one banner.
  const dismissConnectorNotice = useCallback(
    (connectorType: string, action: 'reconnect' | 'rate_limit') => {
      dispatch({ type: 'CONNECTOR_NOTICE_DISMISS', payload: { connectorType, action } });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [] // dispatch stable
  );

  // Derived state (computed from reducer state)
  // Compaction v2 (Task 3.3): `compacting` is treated as an in-flight state so
  // that the existing `disabled={isTyping || isUsageBlocked}` wiring on
  // ChatInput automatically locks the textarea while the server summarizes.
  const isTyping =
    state.status === 'streaming' || state.status === 'sending' || state.status === 'compacting';
  const isConnected = state.apiAvailable && state.streaming.sseStatus !== 'error';

  return {
    messages: state.messages,
    isTyping,
    activeStreamId: state.status === 'streaming' ? state.streaming.currentMessageId : null,
    streamPhase: state.streaming.phase,
    isConnected,
    apiAvailable: state.apiAvailable,
    conversationTotals: state.totals,
    sendMessage,
    clearMessages,
    setMessages,
    appendMessage,
    isLoadingHistory: state.isLoadingHistory,
    // LARS: Registry for rich rendering
    registry: state.registry,
    getRegistryItem,
    // Debug Panel: Scoring metrics for current request
    currentDebugMetrics: state.currentDebugMetrics,
    // Debug Panel: Cumulative history of all request metrics
    debugMetricsHistory: state.debugMetricsHistory,
    // Browser Screenshots: Current overlay data
    browserScreenshot: state.browserScreenshot,
    clearBrowserScreenshot,
    // Context-usage pill: tokens vs compaction threshold (null on first load)
    contextUsage: state.contextUsage,
    hydrateContextUsage,
    // HITL approval card (Lot 1 P1-V1)
    hitl: state.hitl,
    hydratePendingHitl,
    submitHitlDecision,
    // Connector error notices (Lot 3 P3, ADR-134)
    connectorNotices: state.connectorNotices,
    dismissConnectorNotice,
    // ADR-117 Lot 2: background-run reattachment
    resumeActiveRun,
    checkAndResumeActiveRun,
    // ADR-117 Lot 3: stop button
    stopGeneration,
  };
};

import { useReducer, useCallback, useEffect, useRef, Dispatch } from 'react';
import {
  Message,
  MessageAttachmentMeta,
  ChatStreamChunk,
  RegistryItem,
  BrowserContext,
  DebugMetrics,
} from '@/types/chat';
import { ConversationTotals, ChatAction, DebugMetricsEntry } from '@/types/chat-state';
import { chatReducer, createInitialState } from '@/reducers/chat-reducer';
import { validateReducerAction } from '@/reducers/chat-reducer-errors';
import { chatSSEClient } from '@/lib/api/chat';
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
import { processSSEChunk, SSEHandlerContext } from '@/lib/sse-handlers';
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
  isConnected: boolean;
  apiAvailable: boolean;
  conversationTotals: ConversationTotals;
  sendMessage: (
    content: string,
    attachmentIds?: string[],
    attachmentsMeta?: MessageAttachmentMeta[]
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

  /**
   * Validated dispatch wrapper - logs errors before passing to pure reducer.
   * This maintains reducer purity while enabling error detection.
   */
  const dispatch: Dispatch<ChatAction> = useCallback(
    (action: ChatAction) => {
      // Validate action against current state (development only)
      if (process.env.NODE_ENV === 'development') {
        const errors = validateReducerAction(state, action);
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
    },
    [state]
  );

  // HITL streaming buffer (stores partial questions during progressive rendering)
  const hitlQuestionBuffer = useRef<Map<string, string>>(new Map());

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
   * Send a chat message and handle SSE streaming response.
   */
  const sendMessage = useCallback(
    async (
      content: string,
      attachmentIds?: string[],
      attachmentsMeta?: MessageAttachmentMeta[]
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

      const request = {
        message: content,
        user_id: user.id,
        session_id: sessionId,
        context: browserContext,
        ...(attachmentIds && attachmentIds.length > 0 ? { attachment_ids: attachmentIds } : {}),
      };

      try {
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
              assistantMessageId,
              progressMessageId,
              setProgressMessageId: (id: string | null) => {
                progressMessageId = id;
              },
              normalStreamInitialized,
              setNormalStreamInitialized: (v: boolean) => {
                normalStreamInitialized = v;
              },
            };

            // Delegate to extracted SSE handlers (see lib/sse-handlers/)
            processSSEChunk(chunk, handlerContext);
          },
          // onError: Handle SSE connection errors
          (error: Error) => {
            logger.error(
              'chat_sse_error',
              error,
              withContext({
                component: 'useChat',
              })
            );

            // Transition to error state
            dispatch({
              type: 'SSE_ERROR',
              payload: { error: error.message },
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

        // Transition to error state
        dispatch({
          type: 'SSE_ERROR',
          payload: { error: (error as Error).message },
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

  // Derived state (computed from reducer state)
  const isTyping = state.status === 'streaming' || state.status === 'sending';
  const isConnected = state.apiAvailable && state.streaming.sseStatus !== 'error';

  return {
    messages: state.messages,
    isTyping,
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
  };
};

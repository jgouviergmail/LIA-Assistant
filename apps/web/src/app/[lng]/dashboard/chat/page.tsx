'use client';

import { useAuth } from '@/hooks/useAuth';
import { useChat } from '@/hooks/useChat';
import { useConversation, ConversationTotals } from '@/hooks/useConversation';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useNotifications } from '@/hooks/useNotifications';
import { useLiaGender } from '@/hooks/useLiaGender';
import { useDeviceParallax } from '@/hooks/useDeviceParallax';
import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { Message } from '@/types/chat';
import { RegistryProvider } from '@/lib/registry-context';
import { ChatMessageList } from '@/components/chat/ChatMessageList';
import { ChatInput } from '@/components/chat/ChatInput';
import { GeolocationPrompt } from '@/components/chat/GeolocationPrompt';
import { DebugPanel } from '@/components/debug/DebugPanel';
import { useDebugMetrics } from '@/components/debug/hooks/useDebugMetrics';
import { WifiOff, Trash2 } from 'lucide-react';
import { VoiceModeBadge } from '@/components/voice/VoiceModeBadge';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { formatNumber, formatEuro } from '@/lib/format';
import { logger } from '@/lib/logger';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import Image from 'next/image';
import { FeatureErrorBoundary } from '@/components/errors';

import { useDebugPanelEnabled } from '@/hooks/useDebugPanelEnabled';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useUsageLimits } from '@/hooks/useUsageLimits';
import { UsageBlockedBanner } from '@/components/usage/UsageBlockedBanner';
import { ActiveSpacesIndicator } from '@/components/spaces/ActiveSpacesIndicator';

export default function ChatPage() {
  const { user, isLoading } = useAuth();
  const { liaBackgroundImage, mounted: liaImageMounted } = useLiaGender();
  const {
    offset: parallaxOffset,
    isSupported: parallaxSupported,
    hasPermission: parallaxPermission,
    requestPermission: requestParallaxPermission,
  } = useDeviceParallax({
    maxOffset: 15, // pixels
    smoothing: 0.12,
  });
  // Debug Panel: Check if enabled (runtime admin setting only)
  // Must be before useChat so we can pass visibility for viewport_width calculation
  const { isEnabled: debugPanelEnabled } = useDebugPanelEnabled();
  // App config: feature flags from backend /api/v1/config
  const { config: appConfig } = useAppConfig(!!user && !isLoading);

  // Usage limits (per-user quotas)
  const { isBlocked: isUsageBlocked, blockReason: usageBlockReason } = useUsageLimits();

  // Debug panel requires desktop viewport (≥1024px) - not suitable for mobile
  const [isDesktop, setIsDesktop] = useState(false);
  useEffect(() => {
    const mql = window.matchMedia('(min-width: 1024px)');
    setIsDesktop(mql.matches);
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);
  const showDebugPanel = debugPanelEnabled && isDesktop;

  const {
    messages,
    isTyping,
    isConnected,
    apiAvailable,
    conversationTotals: sessionTotals, // Totals accumulated during the current session (SSE done chunks)
    registry, // LARS: registry items for rich rendering (MCP Apps, etc.)
    sendMessage,
    setMessages,
    appendMessage,
    clearMessages,
    currentDebugMetrics, // Debug Panel: Scoring metrics for current request
    debugMetricsHistory, // Debug Panel: Cumulative history of all request metrics
    browserScreenshot, // Browser Screenshots: Current overlay data
  } = useChat({ debugPanelVisible: showDebugPanel });
  const { loadConversationHistory, loadConversationTotals, resetConversation } = useConversation();
  const router = useLocalizedRouter();
  const { t } = useTranslation();
  const [isResetting, setIsResetting] = useState(false);
  const [currentMessage, setCurrentMessage] = useState('');

  // Debug Panel: Get validated metrics for current request
  // SIMPLIFIED (v3.2): Direct storage without messageId indexing
  // Eliminates synchronization issues between frontend/backend IDs
  const {
    metrics: latestDebugMetrics,
    isValid: debugMetricsValid,
    errors: debugMetricsErrors,
  } = useDebugMetrics(currentDebugMetrics);

  // Log diagnostics if issues detected
  useEffect(() => {
    if (showDebugPanel && !debugMetricsValid && debugMetricsErrors.length > 0) {
      logger.warn('chat_page_debug_metrics_issues', {
        errors: debugMetricsErrors,
      });
    }
  }, [showDebugPanel, debugMetricsValid, debugMetricsErrors]);

  // Callback to handle reminder notifications
  // Uses appendMessage instead of reloading history to avoid race conditions
  // during streaming or user input. The message is already archived backend-side.
  const handleReminder = useCallback(
    (content: string, reminderId: string) => {
      // 1. Immediate feedback via toast popup (no icon - already in message)
      toast.info(content, {
        duration: 5000,
      });

      // 2. Append reminder message locally (no API reload needed)
      // The backend has already archived this message in the conversation,
      // so it will be present on next page refresh. This approach:
      // - Avoids race conditions with ongoing streaming
      // - Provides immediate visual feedback
      // - Eliminates unnecessary network requests
      const reminderMessage: Message = {
        id: reminderId || `reminder_${Date.now()}`,
        content: content,
        role: 'assistant',
        timestamp: new Date(),
        metadata: { type: 'reminder_notification' },
      };

      appendMessage(reminderMessage);
    },
    [appendMessage]
  );

  // Callback to handle proactive notifications (interest, heartbeat, future types)
  // Same pattern as reminders: append locally to avoid race conditions
  const handleProactiveNotification = useCallback(
    (content: string, targetId: string, metadata?: Record<string, unknown>) => {
      // 1. Toast: use interest_topic for interest, generic label for heartbeat/other
      // NOTE: decision_reason is internal English LLM reasoning — NOT user-facing
      const topic = metadata?.interest_topic as string | undefined;
      const toastMessage = topic ? `💡 ${topic}` : '💡 Info';
      toast.info(toastMessage, {
        duration: 5000,
        description: content.slice(0, 100) + (content.length > 100 ? '...' : ''),
      });

      // 2. Append proactive message locally with token data from metadata
      const proactiveType = (metadata?.type as string) || 'proactive_interest';
      const proactiveMessage: Message = {
        id: targetId || `proactive_${Date.now()}`,
        content: content,
        role: 'assistant',
        timestamp: new Date(),
        // Populate token fields from metadata (centrally injected by runner)
        tokensIn: metadata?.tokens_in as number | undefined,
        tokensOut: metadata?.tokens_out as number | undefined,
        tokensCache: metadata?.tokens_cache as number | undefined,
        costEur: metadata?.cost_eur as number | undefined,
        metadata: {
          type: proactiveType,
          target_id: targetId,
          ...metadata,
        },
      };

      appendMessage(proactiveMessage);
    },
    [appendMessage]
  );

  // Callback to handle scheduled action execution results
  // Unlike reminders/interests (which send full content via SSE), scheduled actions
  // send truncated content (500 chars) via SSE. The full response is already archived
  // by stream_chat_response, so we reload the conversation history to display it.
  const handleScheduledAction = useCallback(
    async (content: string, _actionId: string, title: string) => {
      // 1. Toast notification with action title
      toast.info(title, {
        duration: 5000,
        description: content.slice(0, 100) + (content.length > 100 ? '...' : ''),
      });

      // 2. Reload full conversation history (result already archived by stream_chat_response)
      try {
        const history = await loadConversationHistory();
        if (history.length > 0) {
          setMessages(history);
        }
      } catch (error) {
        logger.warn('Failed to reload conversation after scheduled action', {
          component: 'ChatPage',
          error: error instanceof Error ? error.message : String(error),
        });
      }
    },
    [loadConversationHistory, setMessages]
  );

  // Connect to SSE notifications for real-time reminders, proactive notifications, and scheduled actions
  // Only connect when user is authenticated (prevents 401 errors on SSE endpoint)
  // SSE now uses relative URL to go through Next.js proxy (same origin)
  // Note: Admin broadcasts are handled by BroadcastProvider (independent SSE/FCM listeners)
  useNotifications({
    enableSSE: true,
    enableFCM: true,
    isAuthenticated: !!user && !isLoading,
    onReminder: handleReminder,
    onProactiveNotification: handleProactiveNotification,
    onScheduledAction: handleScheduledAction,
  });

  // Handle message change from ChatInput (for geolocation prompt detection)
  const handleMessageChange = useCallback((message: string) => {
    setCurrentMessage(message);
  }, []);

  // Totals from API (loaded at startup from message_token_summary)
  // These totals are the source of truth for persisted history
  const [apiTotals, setApiTotals] = useState<ConversationTotals | null>(null);

  // Combined totals: API (history) + Current session (new messages not yet persisted)
  // On refresh, apiTotals contains the full history, sessionTotals is at 0
  // During the session, sessionTotals accumulates new tokens in real time
  const combinedTotals = useMemo(() => {
    // If no API totals loaded, use only session totals
    const apiIn = apiTotals?.total_tokens_in ?? 0;
    const apiOut = apiTotals?.total_tokens_out ?? 0;
    const apiCache = apiTotals?.total_tokens_cache ?? 0;
    const apiCost = apiTotals?.total_cost_eur ?? 0;
    const apiGoogleApi = apiTotals?.total_google_api_requests ?? 0;

    // Session totals are already accumulated by the reducer (STREAM_DONE)
    const sessionIn = sessionTotals.totalTokensIn;
    const sessionOut = sessionTotals.totalTokensOut;
    const sessionCache = sessionTotals.totalTokensCache;
    const sessionCost = sessionTotals.totalCostEur;
    const sessionGoogleApi = sessionTotals.totalGoogleApiRequests;

    return {
      tokensIn: apiIn + sessionIn,
      tokensOut: apiOut + sessionOut,
      tokensCache: apiCache + sessionCache,
      costEur: apiCost + sessionCost,
      googleApiRequests: apiGoogleApi + sessionGoogleApi,
    };
  }, [apiTotals, sessionTotals]);

  // Count all user messages (no HITL filtering - all messages are displayed and counted)
  const userMessageCount = useMemo(() => {
    return messages.filter(msg => msg.role === 'user').length;
  }, [messages]);

  // Verify that the user is active
  useEffect(() => {
    if (!isLoading && user && !user.is_active) {
      router.push('/dashboard');
    }
  }, [user, isLoading, router]);

  // Load conversation history AND totals on mount
  // PERF 2026-01-13: Parallelize API calls for faster page load
  useEffect(() => {
    const loadData = async () => {
      if (user && apiAvailable) {
        // Load history and totals in parallel (independent API calls)
        const [history, totals] = await Promise.all([
          loadConversationHistory(),
          loadConversationTotals(),
        ]);

        if (history.length > 0) {
          setMessages(history);
        }

        // Totals from API (source of truth for full history)
        // These totals include ALL tokens, including those from HITL messages
        if (totals) {
          setApiTotals(totals);
        }
      }
    };

    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, apiAvailable]);

  // Reload messages when app returns from background
  // Fixes: notifications (reminders, proactive) sent while app is backgrounded
  // are not displayed until manual refresh. The OS may drop SSE connection
  // when app is in background to save battery.
  const isReloadingRef = useRef(false);
  const lastMessageCountRef = useRef(0);

  // Track message count for comparison
  useEffect(() => {
    lastMessageCountRef.current = messages.length;
  }, [messages.length]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleVisibilityChange = async () => {
      // Guard: only reload when visible, authenticated, not typing, and not already reloading
      if (
        document.visibilityState !== 'visible' ||
        !user ||
        !apiAvailable ||
        isTyping ||
        isReloadingRef.current
      ) {
        return;
      }

      isReloadingRef.current = true;

      try {
        const history = await loadConversationHistory();

        // Only update if there are new messages (avoid unnecessary re-renders)
        if (history.length > lastMessageCountRef.current) {
          logger.debug('New messages detected on foreground return', {
            component: 'ChatPage',
            previousCount: lastMessageCountRef.current,
            newCount: history.length,
          });
          setMessages(history);
        }
      } catch (error) {
        logger.warn('Failed to reload messages on visibility change', {
          component: 'ChatPage',
          error: error instanceof Error ? error.message : String(error),
        });
      } finally {
        isReloadingRef.current = false;
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [user, apiAvailable, isTyping, loadConversationHistory, setMessages]);

  // Handle conversation reset with confirmation
  const handleResetConversation = async () => {
    if (isResetting) return;

    // Show confirmation dialog
    const confirmed = window.confirm(t('chat.reset_conversation_confirm'));
    if (!confirmed) return;

    setIsResetting(true);
    try {
      await resetConversation();
      clearMessages();
      // Reset API totals (conversation was deleted)
      setApiTotals(null);
      toast.success(t('chat.conversation_reset_success'));
    } catch {
      toast.error(t('chat.conversation_reset_error'));
    } finally {
      setIsResetting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-3">
          <LoadingSpinner size="xl" />
          <p className="text-[13px] mobile:text-sm text-muted-foreground">
            {t('chat.loading_conversation')}
          </p>
        </div>
      </div>
    );
  }

  if (!user?.is_active) {
    return null;
  }

  return (
    <FeatureErrorBoundary feature="chat">
      <div className="flex h-[calc(100vh-5.25rem)] gap-4">
        {/* Main Chat Area */}
        <div
          className={`flex flex-col flex-1 bg-background rounded-xl border border-border/50 shadow-lg overflow-hidden ${showDebugPanel ? 'max-w-[calc(100%-420px)]' : ''}`}
        >
          {/* Header - Enhanced with glassmorphism and shimmer effect */}
          <div className="relative border-b border-border/40 bg-card/95 backdrop-blur-sm px-4 py-4 sm:px-6 shadow-sm header-shimmer">
            <div className="flex items-center justify-between">
              {/* Left side: Status indicator only */}
              {!apiAvailable ? (
                <div className="flex items-center gap-2 rounded-full bg-rose-100 dark:bg-rose-900 px-3 py-1.5 shadow-sm border border-rose-200 dark:border-rose-800">
                  <WifiOff className="h-3.5 w-3.5 text-rose-600 dark:text-rose-300" />
                  <span className="text-[11px] mobile:text-xs font-semibold text-rose-600 dark:text-rose-300">
                    {t('chat.input.status.offline')}
                  </span>
                </div>
              ) : isTyping ? (
                <div className="flex items-center gap-2 rounded-full bg-amber-100 dark:bg-amber-900 px-3 py-1.5 shadow-sm border border-amber-200 dark:border-amber-800">
                  <LoadingSpinner className="h-3.5 w-3.5 text-amber-600 dark:text-amber-300" />
                  <span className="text-[11px] mobile:text-xs font-semibold text-amber-600 dark:text-amber-300">
                    {t('chat.input.status.processing')}
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2 rounded-full bg-green-100 dark:bg-green-900 px-3 py-1.5 shadow-sm border border-green-200 dark:border-green-800">
                  <div className="h-3.5 w-3.5 rounded-full bg-green-500 dark:bg-green-400 animate-pulse" />
                  <span className="text-[11px] mobile:text-xs font-semibold text-green-600 dark:text-green-300">
                    {t('chat.input.status.online')}
                  </span>
                </div>
              )}

              {/* Center: Voice Mode Badge - Single instance, always mounted to preserve KWS state */}
              <div className="absolute left-1/2 -translate-x-1/2">
                <VoiceModeBadge
                  onTranscription={sendMessage}
                  disabled={!apiAvailable || isTyping || isUsageBlocked}
                />
              </div>

              {/* RAG Spaces Indicator */}
              <ActiveSpacesIndicator />

              {/* Right side: Delete/New chat */}
              <div className="flex items-center gap-2">
                {/* Delete/New chat button */}
                <button
                  onClick={handleResetConversation}
                  disabled={isResetting || !apiAvailable}
                  className="flex items-center gap-2 rounded-full bg-rose-100 dark:bg-rose-900 px-3 py-1.5 shadow-sm border border-rose-200 dark:border-rose-800 cursor-pointer transition-colors hover:bg-rose-200 dark:hover:bg-rose-800 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isResetting ? (
                    <LoadingSpinner className="h-3.5 w-3.5 text-rose-600 dark:text-rose-300" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5 text-rose-600 dark:text-rose-300" />
                  )}
                  <span className="text-[11px] mobile:text-xs font-semibold text-rose-600 dark:text-rose-300">
                    {t('chat.new_chat')}
                  </span>
                </button>
              </div>
            </div>
          </div>

          {/* Usage Limit Blocked Banner */}
          {isUsageBlocked && <UsageBlockedBanner blockReason={usageBlockReason} />}

          {/* Conversation Totals Banner - Shows combined totals (API history + current session) */}
          {/* Show if tokens_display_enabled is true and there are tokens */}
          {user?.tokens_display_enabled &&
            (combinedTotals.tokensIn > 0 || combinedTotals.tokensOut > 0) && (
              <div className="hidden mobile:flex bg-muted/50 border-b border-border px-4 py-3 items-center justify-center text-xs">
                <div className="flex items-center gap-4">
                  {/* Total tokens (in + out + cache) */}
                  <span className="text-purple-600">
                    🔢{' '}
                    {formatNumber(
                      combinedTotals.tokensIn +
                        combinedTotals.tokensOut +
                        combinedTotals.tokensCache
                    )}{' '}
                    TOTAL
                  </span>
                  <span className="text-orange-500">
                    🟠 {formatNumber(combinedTotals.tokensIn)} IN
                  </span>
                  <span className="text-green-600">
                    🟢 {formatNumber(combinedTotals.tokensOut)} OUT
                  </span>
                  <span className="text-blue-500">
                    🔵 {formatNumber(combinedTotals.tokensCache)} CACHE
                  </span>
                  <span className="text-purple-500">
                    🟣 {formatNumber(combinedTotals.googleApiRequests)} GOOGLE
                  </span>
                  <span className="text-muted-foreground">|</span>
                  <span className="text-primary font-semibold">
                    {userMessageCount}{' '}
                    {userMessageCount > 1 ? t('chat.page.message_plural') : t('chat.page.message')}
                  </span>
                  <span className="text-muted-foreground">|</span>
                  <span className="text-primary font-bold">
                    {formatEuro(combinedTotals.costEur)}
                  </span>
                </div>
              </div>
            )}

          {/* Messages Area - With fixed LIA background image + parallax effect */}
          <div className="relative flex-1 overflow-hidden">
            {/* Fixed Background Image - with parallax on mobile device tilt */}
            {liaImageMounted && (
              <div
                className="absolute z-0 pointer-events-none transition-transform duration-75 ease-out"
                style={{
                  // Extend beyond bounds to allow parallax movement without showing edges
                  inset: '-20px',
                  transform: `translate(${parallaxOffset.x}px, ${parallaxOffset.y}px)`,
                }}
                // Request iOS permission on first touch
                onTouchStart={() => {
                  if (parallaxSupported && !parallaxPermission) {
                    requestParallaxPermission();
                  }
                }}
              >
                <Image
                  src={liaBackgroundImage}
                  alt=""
                  fill
                  className="object-cover opacity-8 dark:opacity-12"
                  priority
                />
                {/* Gradient overlay for better text readability */}
                <div className="absolute inset-0 bg-gradient-to-b from-background/60 via-background/40 to-background/60" />
              </div>
            )}
            {/* Scrollable messages container with thin scrollbar */}
            <div className="relative z-10 h-full overflow-y-auto chat-scrollbar">
              <RegistryProvider value={registry}>
                <ChatMessageList
                  messages={messages}
                  isTyping={isTyping}
                  browserScreenshot={browserScreenshot}
                />
              </RegistryProvider>
            </div>
          </div>

          {/* Geolocation Prompt - Shows when user types location phrases */}
          <GeolocationPrompt currentMessage={currentMessage} />

          {/* Input Area - Enhanced with elevation */}
          <div className="border-t border-border/40 bg-card/80 backdrop-blur-sm shadow-lg">
            <ChatInput
              onSendMessage={sendMessage}
              disabled={isTyping || isUsageBlocked}
              isConnected={isConnected}
              apiAvailable={apiAvailable && !isUsageBlocked}
              onMessageChange={handleMessageChange}
              attachmentsEnabled={appConfig?.features?.attachments_enabled ?? true}
            />
          </div>
        </div>

        {/* Debug Panel - Right side (only when enabled + desktop viewport ≥1024px) */}
        {showDebugPanel && (
          <div className="w-[400px] bg-background rounded-xl border border-border/50 shadow-lg overflow-hidden">
            <DebugPanel
              key={latestDebugMetrics ? 'has-metrics' : 'no-metrics'}
              metrics={latestDebugMetrics}
              history={debugMetricsHistory}
              className="h-full"
            />
          </div>
        )}
      </div>
    </FeatureErrorBoundary>
  );
}

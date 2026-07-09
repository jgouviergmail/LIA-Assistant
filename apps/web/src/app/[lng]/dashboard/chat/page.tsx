'use client';

import { useAuth } from '@/hooks/useAuth';
import { useChat } from '@/hooks/useChat';
import { useConversation, ConversationTotals } from '@/hooks/useConversation';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useNotifications } from '@/hooks/useNotifications';
import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { Message } from '@/types/chat';
import { RegistryProvider } from '@/lib/registry-context';
import { ChatMessageList } from '@/components/chat/ChatMessageList';
import { ChatInput } from '@/components/chat/ChatInput';
import { ContextUsagePill } from '@/components/chat/ContextUsagePill';
import { GeolocationPrompt } from '@/components/chat/GeolocationPrompt';
import { DebugPanel } from '@/components/debug/DebugPanel';
import { useDebugMetrics } from '@/components/debug/hooks/useDebugMetrics';
import { WifiOff, Trash2, Search, X } from 'lucide-react';
import { VoiceModeBadge } from '@/components/voice/VoiceModeBadge';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { formatNumber, formatEuro } from '@/lib/format';
import { logger } from '@/lib/logger';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { FeatureErrorBoundary } from '@/components/errors';

import { useDebugPanelEnabled } from '@/hooks/useDebugPanelEnabled';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useUsageLimits } from '@/hooks/useUsageLimits';
import { UsageBlockedBanner } from '@/components/usage/UsageBlockedBanner';
import { ActiveSpacesIndicator } from '@/components/spaces/ActiveSpacesIndicator';

export default function ChatPage() {
  const { user, isLoading } = useAuth();
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
    contextUsage, // Context-usage pill: tokens vs compaction threshold
    hydrateContextUsage, // Seeds the pill from /me/totals on page load
    checkAndResumeActiveRun, // ADR-117 Lot 2: silent reattach to an in-flight run
    stopGeneration, // ADR-117 Lot 3: stop button (cancels the in-flight run)
  } = useChat({ debugPanelVisible: showDebugPanel });
  const {
    loadConversationPage,
    loadOlderMessages,
    isLoadingOlder,
    loadConversationTotals,
    resetConversation,
  } = useConversation();

  // Scroll-up pagination state.
  // ``oldestCursor`` is the ``created_at`` of the oldest message currently
  // loaded (``next_cursor`` from the backend). ``hasMoreOlder`` toggles the
  // top sentinel in ChatMessageList. Reset to ``(null, false)`` whenever the
  // history is fully reloaded (initial mount, visibility return, post-action
  // refresh) so pagination state stays in sync with the rendered message list.
  const [oldestCursor, setOldestCursor] = useState<string | null>(null);
  const [hasMoreOlder, setHasMoreOlder] = useState(false);
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
        const page = await loadConversationPage();
        if (page.messages.length > 0) {
          setMessages(page.messages);
        }
        // Reset pagination state — list snaps back to the newest page.
        setHasMoreOlder(page.hasMore);
        setOldestCursor(page.nextCursor);
      } catch (error) {
        logger.warn('Failed to reload conversation after scheduled action', {
          component: 'ChatPage',
          error: error instanceof Error ? error.message : String(error),
        });
      }
    },
    [loadConversationPage, setMessages]
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

  // Client-side history search: filters currently-loaded messages by content.
  // The backend endpoint also supports ?search=... for server-side filtering,
  // but client-side is instant for already-loaded history.
  const [searchQuery, setSearchQuery] = useState('');
  const displayedMessages = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return messages;
    return messages.filter(msg => msg.content.toLowerCase().includes(q));
  }, [messages, searchQuery]);

  // ``setMessages`` accepts only ``Message[]`` (the underlying reducer doesn't
  // support a functional updater). To prepend without staleness we read the
  // current list from a ref kept in sync with the state — this avoids
  // rebuilding ``handleLoadOlder`` on every message append, which would in
  // turn rebind the IntersectionObserver in ChatMessageList on every render.
  const messagesRef = useRef<Message[]>(messages);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // Scroll-up handler — prepends an older page to the message list.
  //
  // Dedup is essential because the same message could come back if the cursor
  // window overlaps (e.g. a new message landed during the fetch and shifted
  // the page boundary). Existing ids in the current ``messages`` are
  // skip-listed before prepending.
  const handleLoadOlder = useCallback(async () => {
    if (!oldestCursor || !hasMoreOlder) return;
    const page = await loadOlderMessages(oldestCursor);
    if (page.messages.length === 0) {
      // Even an empty page must commit ``hasMore=false`` so the sentinel stops
      // firing — without this the IntersectionObserver would loop forever at
      // the start of the conversation.
      setHasMoreOlder(page.hasMore);
      setOldestCursor(page.nextCursor);
      return;
    }
    const current = messagesRef.current;
    const seen = new Set(current.map(m => m.id));
    const fresh = page.messages.filter(m => !seen.has(m.id));
    setMessages([...fresh, ...current]);
    setHasMoreOlder(page.hasMore);
    setOldestCursor(page.nextCursor);
  }, [oldestCursor, hasMoreOlder, loadOlderMessages, setMessages]);

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
        // Load first page (with pagination metadata) and totals in parallel
        const [page, totals] = await Promise.all([
          loadConversationPage(),
          loadConversationTotals(),
        ]);

        if (page.messages.length > 0) {
          setMessages(page.messages);
        }
        setHasMoreOlder(page.hasMore);
        setOldestCursor(page.nextCursor);

        // Totals from API (source of truth for full history)
        // These totals include ALL tokens, including those from HITL messages
        if (totals) {
          setApiTotals(totals);
          // Context-usage pill (2026-05): hydrate from the same payload so the
          // pill is visible immediately on page refresh, not only after the
          // first new SSE `done` event.
          hydrateContextUsage(totals.context_tokens, totals.context_threshold);
        }

        // ADR-117 Lot 2: a generation may still be running in the background
        // (the user navigated away mid-run). Silently reattach AFTER the
        // history is rendered so the in-progress bubble lands below its
        // already-persisted user message (product decision: auto-resume).
        await checkAndResumeActiveRun();
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
        const page = await loadConversationPage();

        // ADR-117 Lot 2: the OS may have dropped the SSE subscription while
        // backgrounded — if the run is still going, silently reattach (the
        // isTyping guard above already skips this when a stream is active).
        const resumed = await checkAndResumeActiveRun();

        // Update when there are new messages (avoid unnecessary re-renders)
        // OR when a resume just started: a connection dropped mid-stream may
        // have left a stale partial bubble + error bubble behind — replace
        // with DB truth so the resumed bubble isn't duplicated. The reducer's
        // SET_MESSAGES anti-race guard preserves the resuming bubble itself.
        if (page.messages.length > lastMessageCountRef.current || resumed) {
          logger.debug('New messages detected on foreground return', {
            component: 'ChatPage',
            previousCount: lastMessageCountRef.current,
            newCount: page.messages.length,
            resumed,
          });
          setMessages(page.messages);
          // Pagination state aligned with the freshly loaded newest page.
          setHasMoreOlder(page.hasMore);
          setOldestCursor(page.nextCursor);
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
  }, [user, apiAvailable, isTyping, loadConversationPage, setMessages, checkAndResumeActiveRun]);

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
      // Pagination state must follow the now-empty conversation.
      setHasMoreOlder(false);
      setOldestCursor(null);
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
                  onTranscription={(text, meta) => sendMessage(text, undefined, undefined, meta)}
                  disabled={!apiAvailable || isTyping || isUsageBlocked}
                />
              </div>

              {/* RAG Spaces Indicator */}
              <ActiveSpacesIndicator />

              {/* Right side: Search + Context-usage pill + Delete/New chat */}
              <div className="flex items-center gap-2">
                {/* Search input — filters currently loaded messages by content */}
                <div className="relative hidden mobile:flex items-center">
                  <Search className="absolute left-2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
                  <input
                    type="search"
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    placeholder={t('conversations.search_placeholder')}
                    aria-label={t('conversations.search_placeholder')}
                    className="h-8 w-48 pl-7 pr-7 text-xs rounded-full bg-background border border-border focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => setSearchQuery('')}
                      aria-label={t('conversations.search_clear')}
                      className="absolute right-1 p-0.5 rounded-full hover:bg-muted"
                    >
                      <X className="h-3 w-3 text-muted-foreground" />
                    </button>
                  )}
                </div>
                {/* Context-usage pill — shows tokens vs compaction threshold.
                    Hidden until the first turn completes (no data yet).
                    Placed AFTER the search field so on desktop the order is
                    [Search] [Pill] [Delete]. */}
                {contextUsage && <ContextUsagePill usage={contextUsage} />}
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

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto chat-scrollbar">
            <RegistryProvider value={registry}>
              <ChatMessageList
                messages={displayedMessages}
                isTyping={isTyping && !searchQuery}
                browserScreenshot={browserScreenshot}
                // Scroll-up pagination — disabled while the user is searching
                // (search filters client-side over already-loaded messages
                // only, so a sentinel would conflate "no match in this page"
                // with "more remote history exists").
                hasMoreOlder={hasMoreOlder && !searchQuery}
                isLoadingOlder={isLoadingOlder}
                onLoadOlder={handleLoadOlder}
              />
            </RegistryProvider>
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
              isGenerating={isTyping}
              onStopGeneration={stopGeneration}
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

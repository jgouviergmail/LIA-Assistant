'use client';

import { useAuth } from '@/hooks/useAuth';
import { useChat } from '@/hooks/useChat';
import { useConversation, ConversationTotals } from '@/hooks/useConversation';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useNotifications } from '@/hooks/useNotifications';
import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useSearchParams, type ReadonlyURLSearchParams } from 'next/navigation';
import { Message } from '@/types/chat';
import { RegistryProvider } from '@/lib/registry-context';
import { mergeRegistryWithHistory } from '@/lib/message-widgets';
import { ChatMessageList } from '@/components/chat/ChatMessageList';
import { PsycheMilestoneWatcher } from '@/components/psyche/PsycheMilestoneWatcher';
import { useLiveTabTitle } from '@/hooks/useLiveTabTitle';
import { ChatInput } from '@/components/chat/ChatInput';
import { ContextUsagePill } from '@/components/chat/ContextUsagePill';
import { ChatSearchBar } from '@/components/chat/search/ChatSearchBar';
import { useChatHistorySearch } from '@/hooks/useChatHistorySearch';
import { DebugPanel } from '@/components/debug/DebugPanel';
import { useDebugMetrics } from '@/components/debug/hooks/useDebugMetrics';
import { WifiOff, Trash2, Search, X } from 'lucide-react';
import { VoiceModeBadge } from '@/components/voice/VoiceModeBadge';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { logger } from '@/lib/logger';
import { toPlainPreview, NOTIFICATION_PREVIEW_MAX_LENGTH } from '@/lib/notification-preview';
import { sentHistoryOf } from '@/lib/sent-history';
import { hitlAwaitsUser, visibleChatSurfaces } from '@/lib/chat-surfaces';
import { visibleFollowups } from '@/components/chat/FollowupChips';
import { ChatConditionalSurfaces } from '@/components/chat/ChatConditionalSurfaces';
import { SelectionActions } from '@/components/chat/SelectionActions';
import { ResetConversationConfirm } from '@/components/chat/ResetConversationConfirm';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { FeatureErrorBoundary } from '@/components/errors';

import { useDebugPanelEnabled } from '@/hooks/useDebugPanelEnabled';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useInputDraft } from '@/hooks/useInputDraft';
import { useSkills } from '@/hooks/useSkills';
import {
  buildStaticSlashCommands,
  userShortcutCommands,
  type SlashCommand,
} from '@/lib/slash-commands';
import { useChatShortcuts } from '@/hooks/useChatShortcuts';
import { useAutoSendIntent } from '@/hooks/useAutoSendIntent';
import { useDeepLinkParams } from '@/hooks/useDeepLinkParams';
import type { CapabilityDirectiveWire } from '@/types/directive';
import { useUsageLimits } from '@/hooks/useUsageLimits';
import { UsageBanners } from '@/components/usage/UsageBanners';
import { ActiveCallBanner } from '@/components/telephony/ActiveCallBanner';
import { ActiveSpacesIndicator } from '@/components/spaces/ActiveSpacesIndicator';

/**
 * Resolve the chat input's initial text: the `?draft=` deep link (onboarding
 * volet B / briefing intents) wins over the persisted per-user draft
 * (UXR Lot 2, A7). Returns undefined when neither exists so the input keeps
 * its default empty state. Never auto-sent.
 */
function resolveInitialMessage(
  searchParams: ReadonlyURLSearchParams | null,
  storedDraft: string | undefined
): string | undefined {
  const draft = searchParams?.get('draft');
  return draft && draft.trim() ? draft : storedDraft;
}

/** Short locale of an i18n language tag ("fr-FR" → "fr"; default "fr"). */
function shortLang(language: string | undefined): string {
  return (language || 'fr').split('-')[0];
}

/**
 * Toast title + tint for a proactive push (module-level — CC discipline).
 * Peer notifications (Lot 7) reuse their chat-bubble tint so they read as
 * "peer" at a glance; interests title with their topic; the rest stays generic.
 * NOTE: decision_reason is internal English LLM reasoning — NOT user-facing.
 */
function proactiveToastPresentation(metadata?: Record<string, unknown>): {
  message: string;
  className: string | undefined;
} {
  const isPeer =
    typeof metadata?.type === 'string' && (metadata.type as string).startsWith('proactive_peer');
  const peerName = (metadata?.sender_name ?? metadata?.peer_name) as string | undefined;
  const topic = metadata?.interest_topic as string | undefined;
  return {
    message: isPeer ? `🤝 ${peerName || 'Info'}` : topic ? `💡 ${topic}` : '💡 Info',
    className: isPeer ? '!bg-primary/10 !border-primary/25' : undefined,
  };
}

export default function ChatPage() {
  const { user, isLoading } = useAuth();
  const searchParams = useSearchParams();
  // Debug Panel: Check if enabled (runtime admin setting only)
  // Must be before useChat so we can pass visibility for viewport_width calculation
  const { isEnabled: debugPanelEnabled } = useDebugPanelEnabled();
  // Auth resolved AND a user present — the single readiness signal reused by
  // the app-config fetch and the QW-24 intent auto-send (one `&&`, not two).
  const authReady = !!user && !isLoading;
  // App config: feature flags from backend /api/v1/config
  const { config: appConfig } = useAppConfig(authReady);

  // Usage limits (per-user quotas)
  const {
    isBlocked: isUsageBlocked,
    blockReason: usageBlockReason,
    limits: usageLimits,
  } = useUsageLimits();

  // UXR Lot 2 (A7): per-user persisted input draft. The layout mounts this
  // page only once the user is resolved, so the one-shot read is reliable.
  const { initialDraft, saveDraft } = useInputDraft(user);

  // QW-9 / UXR Lot 2 (A7) / N-13 / QW-24 (ADR-173): the one-shot deep links,
  // read live and cleared through the router. Both rules and the production
  // defect that paid for them are documented in the hook.
  const { spotlightVoice, pendingIntent, pendingDirective, clearIntent } =
    useDeepLinkParams(saveDraft);

  // True once the mount history load has SETTLED (loaded, empty, or failed).
  //
  // Production, 2026-08-01: a second chained 360° showed its answer without the
  // question. `?intent=` was auto-sent as soon as auth and the API were ready —
  // which can be BEFORE the history GET returns — and the reply below then did
  // `setMessages(page.messages)` with a server list that predated the send,
  // wiping the optimistic bubble. The message was persisted all along (it came
  // back on refresh); only the browser's list lost it. Gating the send on this
  // flag removes the race instead of merging lists afterwards.
  const [historySettled, setHistorySettled] = useState(false);

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
    activeStreamId, // Assistant message currently streaming (steps/caret styling)
    streamPhase, // 'progress' (execution steps) vs 'answer' (real tokens)
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
    hitl, // HITL approval card state (Lot 1 P1-V1)
    submitHitlDecision, // One-click approval (structured decision, classifier bypassed)
    hydratePendingHitl, // Card rehydration after reload (GET /agents/hitl/pending)
    connectorNotices, // Connector error banners (Lot 3 P3, ADR-134)
    dismissConnectorNotice,
  } = useChat({ debugPanelVisible: showDebugPanel });

  // Blink the tab title while LIA works and the tab is in the background (I5)
  useLiveTabTitle(isTyping);

  const {
    loadConversationPage,
    loadOlderMessages,
    searchMessages,
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
  const { t, i18n } = useTranslation();
  const lng = shortLang(i18n.language);
  const [isResetting, setIsResetting] = useState(false);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
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
      // Flattened for the toast only: the appended chat message below keeps the
      // original content so ReactMarkdown renders it normally.
      toast.info(toPlainPreview(content), {
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
      // 1. Toast — title/tint derived module-level (peers vs interest vs generic)
      const presentation = proactiveToastPresentation(metadata);
      toast.info(presentation.message, {
        duration: 5000,
        description: toPlainPreview(content, NOTIFICATION_PREVIEW_MAX_LENGTH),
        className: presentation.className,
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
        description: toPlainPreview(content, NOTIFICATION_PREVIEW_MAX_LENGTH),
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

  // Handle message change from ChatInput (geolocation prompt detection +
  // draft persistence — debounced, empty clears immediately).
  const handleMessageChange = useCallback(
    (message: string) => {
      setCurrentMessage(message);
      saveDraft(message);
    },
    [saveDraft]
  );

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

  // Chat history search (QW-2): instant accent-insensitive client filter,
  // in-bubble highlight, whole-history server search with jump-to-result and
  // the "history view" state. All feature logic lives in the hook.
  const {
    searchQuery,
    setSearchQuery,
    highlightTerm,
    displayedMessages,
    loadedMatchCount,
    serverSearchAvailable,
    panelOpen,
    serverResults,
    serverHasMore,
    serverLoading,
    serverError,
    runServerSearch,
    loadMoreServerResults,
    closePanel,
    historyView,
    jumpToResult,
    returnToPresent,
    ensurePresent,
  } = useChatHistorySearch({
    messages,
    isTyping,
    hasMoreOlder,
    searchMessages,
    loadOlderMessages,
    loadConversationPage,
    setMessages,
    setHasMoreOlder,
    setOldestCursor,
  });
  // Mobile (< 880px): the header shows a 🔍 toggle; the input row unfolds in
  // the ChatSearchBar. Desktop keeps the inline header field.
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);

  // UXR Lot 3 (A3): explicit own-send signal for the scroll-follow decision —
  // incremented on every real chat send (see ChatMessageList.ownSendTick).
  const [ownSendTick, setOwnSendTick] = useState(0);

  // Arbitration #1 (QW-2): sending while viewing a past point of history
  // first returns to the present so the new turn lands at the bottom of the
  // real conversation, never inside a jumped-to page.
  const sendMessageFromPresent = useCallback(
    async (...args: Parameters<typeof sendMessage>) => {
      await ensurePresent();
      setOwnSendTick(tick => tick + 1);
      return sendMessage(...args);
    },
    [ensurePresent, sendMessage]
  );

  // Widgets persisted on their message (ADR-137) are merged UNDER the live
  // registry, so a conversation reopened from history renders its skill frames
  // and MCP apps instead of an "unavailable" box. The live stream wins on
  // conflict: it is the current turn's truth.
  const registryWithHistory = useMemo(
    () => mergeRegistryWithHistory(registry, messages),
    [registry, messages]
  );

  // UXR Lot 2 (A7, extended): past sent messages — ↑/↓ in the input walk
  // through them (ChatInput owns the key handling).
  const sentHistory = useMemo(() => sentHistoryOf(messages), [messages]);

  // W3: replay a failed prompt. It goes through `sendMessageFromPresent`, the
  // exact path a typed message takes — the retry must not be a second, subtly
  // different send route (history view, own-send tick, HITL resolution all
  // depend on it).
  const handleRetry = useCallback(
    (prompt: string) => {
      void sendMessageFromPresent(prompt);
    },
    [sendMessageFromPresent]
  );

  // QW-24 (ADR-173): auto-send the captured `?intent=`. Quota-blocked
  // sessions degrade to a persisted draft — saved, said out loud, never
  // force-fed past the wall.
  const intentFallbackToDraft = useCallback(
    (text: string) => {
      saveDraft(text);
      toast.info(t('chat.intent_saved_as_draft'));
    },
    [saveDraft, t]
  );
  // The auto-send's `send` takes (text, directive) — the directive is the SIXTH
  // positional argument of `sendMessage`, so this adapter names the gap rather
  // than making the hook know about attachments and STT metadata it has none of.
  const sendIntent = useCallback(
    (text: string, directive?: CapabilityDirectiveWire) =>
      sendMessageFromPresent(text, undefined, undefined, undefined, undefined, directive),
    [sendMessageFromPresent]
  );
  useAutoSendIntent({
    intent: pendingIntent,
    directive: pendingDirective,
    // The settled history IMPLIES auth (the load only runs for a resolved
    // user): sending before the list is in place lets the history load
    // overwrite the very message the user just asked for.
    ready: historySettled,
    apiAvailable,
    isTyping,
    isUsageBlocked,
    send: sendIntent,
    fallbackToDraft: intentFallbackToDraft,
    // Cleared only ONCE ACTED ON: clearing it on arrival races the readiness
    // gate above, and the request evaporates before anything can send it.
    onConsumed: clearIntent,
  });

  // UXR Lot 3 (A3): stable handler for the floating button's history-view
  // delegation (returnToPresent owns its own in-flight guard).
  const handleReturnToPresent = useCallback(() => {
    void returnToPresent();
  }, [returnToPresent]);

  // UXR Lot 8 (A4) + SLASH admin: slash-command registry — the static table
  // (declared once in lib/slash-commands, QA 2026-07-23), the user's own
  // shortcuts (server-persisted; statics win on a legacy id collision), then
  // the dialogue-flagged skills (ADR-118). All labels localized here.
  const { skills } = useSkills();
  const { shortcuts: userShortcuts } = useChatShortcuts();
  const slashCommands = useMemo<SlashCommand[]>(() => {
    const statics = buildStaticSlashCommands(t);
    const dialogueSkills = skills
      .filter(skill => skill.dialogue && skill.enabled_for_user)
      .map<SlashCommand>(skill => ({
        id: `skill:${skill.name}`,
        kind: 'conversational',
        label: skill.name,
        description: skill.descriptions?.[lng] ?? skill.description,
        insertText: t('chat.slash.skill_intent', { name: skill.name }),
      }));
    return [...statics, ...userShortcutCommands(userShortcuts), ...dialogueSkills];
  }, [t, skills, lng, userShortcuts]);
  const handleLocalCommand = useCallback(
    (commandId: string) => {
      if (commandId === 'briefing') router.push('/dashboard');
      if (commandId === 'search') {
        // Mobile: the search row auto-focuses itself on mount. Desktop: the
        // header input is already mounted — focus it via its OWN marker
        // (a bare input[type=search] selector could catch a foreign field).
        setMobileSearchOpen(true);
        requestAnimationFrame(() => {
          document.querySelector<HTMLElement>('input[data-chat-search]')?.focus();
        });
      }
    },
    [router]
  );

  // UXR Lot 4 (A2): follow-up chips — latest answer only, hidden while the
  // surface is transiently busy (streaming, history view); a chip click
  // PREFILLS the input (never sends). Whether they may take the slot at all is
  // decided by the surface arbiter below, not here.
  const followupSuggestions = useMemo(
    () => visibleFollowups(messages, isTyping || !!activeStreamId || historyView),
    [messages, isTyping, activeStreamId, historyView]
  );

  // S1: single priority rule for everything stacked between the thread and the
  // composer. Measured (S0): a pending HITL card plus chips takes the chrome to
  // 443 px of a 716 px shell. More importantly, the combination is incoherent —
  // LIA cannot ask for a confirmation and offer unrelated follow-ups at once.
  // Blocking surfaces are never suppressed; comfort ones yield.
  const chatSurfaces = useMemo(
    () =>
      visibleChatSurfaces({
        usageBlocked: isUsageBlocked,
        hitlAwaitingAction: hitlAwaitsUser(hitl.status),
        hasConnectorNotices: connectorNotices.length > 0,
        // The prompt owns its own trigger; this only offers it the slot.
        wantsGeolocationPrompt: true,
        hasFollowups: followupSuggestions.length > 0,
      }),
    [isUsageBlocked, hitl.status, connectorNotices.length, followupSuggestions.length]
  );
  const [chipPrefill, setChipPrefill] = useState({ text: '', nonce: 0 });
  const handleFollowupPick = useCallback((text: string) => {
    setChipPrefill(prev => ({ text, nonce: prev.nonce + 1 }));
  }, []);

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
      if (!user || !apiAvailable) return;
      // `finally`, always: the auto-send waits for this flag, so a history load
      // that FAILS must still release it — a deep-linked request that never
      // leaves is a worse failure than a list that is momentarily stale.
      try {
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
        const resumed = await checkAndResumeActiveRun();

        // HITL approval card (Lot 1 P1-V1): rebuild the card after a reload —
        // the interrupt metadata chunk is not part of archived history. When a
        // live run was reattached, its replay re-arms the card itself.
        if (!resumed) {
          await hydratePendingHitl();
        }
      } finally {
        setHistorySettled(true);
      }
    };

    void loadData();
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

  // W4a: the confirmation is an in-app AlertDialog, not `window.confirm` — an
  // OS dialog ignores the theme, the chosen typography and the app's language
  // (its buttons come from the operating system), and it blocks the thread.
  // This runs AFTER the user confirmed; the dialog owns that decision.
  const handleResetConversation = async () => {
    if (isResetting) return;
    setResetConfirmOpen(false);
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
      {/* The shell is sized on the DYNAMIC viewport: `100vh` is the height the
          page would have with the browser's URL bar retracted, so while that
          bar is visible — the state a page loads in on mobile — the bottom of
          this container, i.e. the composer, sits below the fold. `dvh` tracks
          the bar. The `vh` declaration stays as the fallback: unlike the
          `max-h` caps elsewhere, losing this one entirely would collapse the
          flex column, so it degrades to the old behaviour rather than to none.

          `--connector-banner-h` is the height of the connector-health banner
          the dashboard layout may insert ABOVE this shell; it defaults to 0px,
          so this arithmetic is unchanged whenever no banner is mounted. Without
          it, a broken connector would push the composer below the fold — the
          constant above cannot know about a block added after it was written. */}
      <div className="flex h-[calc(100vh-5.25rem-var(--connector-banner-h,0px))] supports-[height:100dvh]:h-[calc(100dvh-5.25rem-var(--connector-banner-h,0px))] gap-4">
        {/* Main Chat Area */}
        <div
          className={`flex flex-col flex-1 bg-background rounded-xl border border-border/50 shadow-lg overflow-hidden ${showDebugPanel ? 'max-w-[calc(100%-420px)]' : ''}`}
        >
          {/* Messages area. The header + search + banner block is STICKY INSIDE
              this scroll container (2026-07-30): backdrop-blur only renders
              what actually passes behind the surface, and this chat shell is a
              fixed-height flex column — with the header as a sibling above the
              scroll area, nothing ever slid beneath it and the frosted glass
              stayed invisible. In here, bubbles genuinely scroll under it. */}
          {/* A flex COLUMN scroll container, so the composer below can be
              `sticky bottom-0` and still behave on a short conversation: with
              plain block flow a sticky footer only pins once the content
              overflows, so two messages would leave it floating mid-card. The
              growing middle fills the gap instead. */}
          <div className="flex flex-1 flex-col overflow-y-auto chat-scrollbar">
            <div className="sticky top-0 z-20">
              {/* Frosted-glass header: translucent card + strong blur, no gradient. */}
              <div className="relative border-b border-border/30 bg-card/60 backdrop-blur-xl px-4 py-4 sm:px-6 shadow-sm">
                {/* Three IN-FLOW columns with equal-weight (`flex-1`) sides and a
                `shrink-0` middle: the middle (voice + spaces) is CENTRED when
                the sides are balanced, and SHIFTS by itself — never overlaps —
                when a side grows (the processing / listening status pill, the
                search field). The former `absolute left-1/2` centring reserved
                no width and overlapped the left group; equal flex sides give
                the same visual centring while reflowing automatically. */}
                <div className="flex items-center gap-2">
                  {/* Left side: status pill + search, in that order. The status
                  only renders when it carries information (QW-12) — the
                  nominal "online" state is silent; offline and processing are
                  the exceptional states worth a pill, shown LEFT of the
                  search field. `min-w-0 flex-1` lets this side truncate first
                  so the centred group keeps its place. */}
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    {!apiAvailable ? (
                      <div className="flex items-center gap-2 rounded-full bg-rose-100 dark:bg-rose-900 px-3 py-1.5 shadow-sm border border-rose-200 dark:border-rose-800 shrink-0">
                        <WifiOff className="h-3.5 w-3.5 text-rose-700 dark:text-rose-300" />
                        <span className="text-[11px] mobile:text-xs font-semibold text-rose-700 dark:text-rose-300">
                          {t('chat.input.status.offline')}
                        </span>
                      </div>
                    ) : isTyping ? (
                      <div className="flex items-center gap-2 rounded-full bg-amber-100 dark:bg-amber-900 px-3 py-1.5 shadow-sm border border-amber-200 dark:border-amber-800 shrink-0">
                        <LoadingSpinner className="h-3.5 w-3.5 text-amber-700 dark:text-amber-300" />
                        <span className="text-[11px] mobile:text-xs font-semibold text-amber-700 dark:text-amber-300">
                          {t('chat.input.status.processing')}
                        </span>
                      </div>
                    ) : null}
                    {/* Mobile search toggle (< 880px) — unfolds the input row in
                    the ChatSearchBar below the header (QW-2). */}
                    <button
                      type="button"
                      onClick={() => setMobileSearchOpen(open => !open)}
                      aria-expanded={mobileSearchOpen}
                      aria-label={t('chat.search.open_mobile')}
                      className="mobile:hidden p-2 rounded-full hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <Search className="h-4 w-4 text-muted-foreground" aria-hidden />
                    </button>
                    {/* Search input (≥ 880px) — filters currently loaded messages
                    by content; left-aligned in the header. */}
                    <div className="relative hidden mobile:flex items-center">
                      <Search className="absolute left-2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
                      <input
                        type="search"
                        data-chat-search
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
                  </div>

                  {/* Centre (in flow, shrink-0): Voice Mode Badge — single
                  instance, always mounted to preserve KWS state — and, beside
                  it, the active-spaces pill. `shrink-0` keeps them intact while
                  the flex-1 sides absorb the width; equal sides keep them
                  visually centred and let them SHIFT rather than overlap when a
                  side grows. Discreet, homogeneous pill styling on the
                  indicator. */}
                  <div className="flex shrink-0 items-center gap-2">
                    <VoiceModeBadge
                      onTranscription={(text, meta) =>
                        sendMessageFromPresent(text, undefined, undefined, meta)
                      }
                      disabled={!apiAvailable || isTyping || isUsageBlocked}
                    />
                    <ActiveSpacesIndicator />
                  </div>

                  {/* Right side: context-usage pill + Delete/New chat, in flow.
                  `min-w-0 flex-1` mirrors the left side so the centre stays
                  centred; `justify-end` keeps these pinned to the right edge. */}
                  <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
                    {/* Context-usage pill — shows tokens vs compaction threshold.
                    Hidden until the first turn completes (no data yet).
                    Desktop order on this side: [Pill] [Delete]. Conversation
                    totals ride its tooltip (QW-12) — the dedicated banner
                    line is gone.

                    Below `mobile` (880 px) it steps aside: it is OBSERVATION,
                    and the row must keep room for the search toggle, the
                    spaces indicator and the destructive action. Its tooltip is
                    a hover affordance anyway — unavailable on touch — and the
                    same totals live on the dashboard usage tile. */}
                    {contextUsage && (
                      <div className="hidden mobile:block">
                        <ContextUsagePill
                          usage={contextUsage}
                          totals={
                            user?.tokens_display_enabled &&
                            (combinedTotals.tokensIn > 0 || combinedTotals.tokensOut > 0)
                              ? { ...combinedTotals, userMessageCount }
                              : null
                          }
                        />
                      </div>
                    )}
                    {/* Delete/New chat button. Below `sm` the label steps aside —
                    the row cannot carry it next to the spaces indicator — so
                    the accessible name is carried explicitly: a bare trash
                    icon names nothing. The ACTION itself never disappears; it
                    is destructive and the only way to start over. */}
                    <button
                      onClick={() => setResetConfirmOpen(true)}
                      disabled={isResetting || !apiAvailable}
                      aria-label={t('chat.new_chat')}
                      className="flex shrink-0 items-center gap-2 rounded-full bg-rose-100 dark:bg-rose-900 px-3 py-1.5 shadow-sm border border-rose-200 dark:border-rose-800 cursor-pointer transition-colors hover:bg-rose-200 dark:hover:bg-rose-800 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isResetting ? (
                        <LoadingSpinner className="h-3.5 w-3.5 text-rose-700 dark:text-rose-300" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5 text-rose-700 dark:text-rose-300" />
                      )}
                      <span className="hidden sm:inline text-[11px] mobile:text-xs font-semibold text-rose-700 dark:text-rose-300">
                        {t('chat.new_chat')}
                      </span>
                    </button>
                  </div>
                </div>
              </div>

              {/* History search surface (QW-2): mobile input row, match counter,
              whole-history results panel, history-view banner. */}
              <ChatSearchBar
                searchQuery={searchQuery}
                setSearchQuery={setSearchQuery}
                loadedMatchCount={loadedMatchCount}
                serverSearchAvailable={serverSearchAvailable}
                panelOpen={panelOpen}
                serverResults={serverResults}
                serverHasMore={serverHasMore}
                serverLoading={serverLoading}
                serverError={serverError}
                excerptTerm={highlightTerm || searchQuery}
                historyView={historyView}
                jumpDisabled={isTyping}
                mobileOpen={mobileSearchOpen}
                onCloseMobile={() => setMobileSearchOpen(false)}
                onRunServerSearch={runServerSearch}
                onLoadMoreServerResults={loadMoreServerResults}
                onClosePanel={closePanel}
                onJump={jumpToResult}
                onReturnToPresent={returnToPresent}
              />

              {/* Quota surface: the wall, or the A5 warning that precedes it —
              never both (UsageBanners owns that rule). */}
              {/* A6: while LIA is on the phone, say so — the chat used to go
              completely silent between the confirmation and the recap. */}
              <ActiveCallBanner lng={lng} conversationTick={messages.length} />
              <UsageBanners
                limits={usageLimits}
                isBlocked={isUsageBlocked}
                blockReason={usageBlockReason}
              />
            </div>

            <RegistryProvider value={registryWithHistory}>
              {/* Headless: celebrates relationship-stage milestones (I7) */}
              <PsycheMilestoneWatcher />
              {/* C-02: act on a selected passage of an assistant answer —
                  executes through the same send path as a typed message
                  (ADR-173), or prefills when the action needs the user's
                  own words. Renders nothing without a scoped selection. */}
              {/* `grow shrink-0`: takes the leftover height when the thread is
                  short (which keeps the sticky composer at the bottom), and
                  keeps its own content height when it is long (`shrink-0`, or
                  a flex item would compress and clip the messages). */}
              <div className="flex grow shrink-0 flex-col">
                <SelectionActions
                  onExecute={sendMessageFromPresent}
                  onPrefill={handleFollowupPick}
                />
                <ChatMessageList
                  messages={displayedMessages}
                  isTyping={isTyping && !searchQuery}
                  activeStreamId={searchQuery ? null : activeStreamId}
                  streamPhase={streamPhase}
                  browserScreenshot={browserScreenshot}
                  // Scroll-up pagination — disabled while the user is searching
                  // (search filters client-side over already-loaded messages
                  // only, so a sentinel would conflate "no match in this page"
                  // with "more remote history exists").
                  hasMoreOlder={hasMoreOlder && !searchQuery}
                  isLoadingOlder={isLoadingOlder}
                  onLoadOlder={handleLoadOlder}
                  searchHighlight={highlightTerm}
                  // UXR Lot 3 (A3): floating return button — in history view it
                  // delegates to the QW-2 return-to-present page swap.
                  historyView={historyView}
                  onReturnToPresent={handleReturnToPresent}
                  ownSendTick={ownSendTick}
                  onRetry={handleRetry}
                  onPrefillComposer={handleFollowupPick}
                  // W8: an empty chat offers three ways in. Same rail as the
                  // follow-up chips — it prefills the composer, never sends.
                  onStarterPick={handleFollowupPick}
                />
              </div>
            </RegistryProvider>

            {/* Frosted-glass footer, STICKY INSIDE the same scroll container as
                the header (owner request 2026-07-30). The material only reads
                as glass when something passes behind it, and as a sibling below
                the scroll area nothing ever did — the exact reason the header
                was moved in here. Same tokens as the header, so the two edges
                of the thread are one material. */}
            <div className="sticky bottom-0 z-20">
              {/* Conditional surfaces between the thread and the composer, gated by
                  the S1 arbiter. Extracted as one element on purpose: four inline
                  branches here would grow this render hotspot past its complexity
                  cap, and the band is a subject of its own. */}
              <ChatConditionalSurfaces
                surfaces={chatSurfaces}
                followupSuggestions={followupSuggestions}
                onFollowupPick={handleFollowupPick}
                currentMessage={currentMessage}
                hitl={hitl}
                onHitlAction={submitHitlDecision}
                connectorNotices={connectorNotices}
                onDismissConnectorNotice={dismissConnectorNotice}
              />

              {/* No background here: `ChatInput` owns the glass material (its
                  own root used to paint an opaque `bg-card` over anything set
                  at this level). This wrapper is positioning only. */}
              <div className="shadow-sm">
                <ChatInput
                  initialMessage={resolveInitialMessage(searchParams, initialDraft)}
                  sentHistory={sentHistory}
                  prefill={chipPrefill}
                  slashCommands={slashCommands}
                  onLocalCommand={handleLocalCommand}
                  spotlightVoice={spotlightVoice}
                  onSendMessage={sendMessageFromPresent}
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
          </div>
        </div>

        <ResetConversationConfirm
          open={resetConfirmOpen}
          onOpenChange={setResetConfirmOpen}
          onConfirm={handleResetConversation}
        />

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

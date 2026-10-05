'use client';

import { useAuth } from '@/hooks/useAuth';
import { useChat } from '@/hooks/useChat';
import { useConversation, type ConversationTotals } from '@/hooks/useConversation';
import { useChatServerSync } from '@/hooks/useChatServerSync';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
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
import { ResizableDebugPanel } from '@/components/debug/ResizableDebugPanel';
import { useDebugMetrics } from '@/components/debug/hooks/useDebugMetrics';
import { WifiOff, Trash2, Search, X } from 'lucide-react';
import { VoiceModeBadge } from '@/components/voice/VoiceModeBadge';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { logger } from '@/lib/logger';
import { sentHistoryOf } from '@/lib/sent-history';
import { hitlAwaitsUser, visibleChatSurfaces } from '@/lib/chat-surfaces';
import { visibleFollowups, visibleMotivation } from '@/components/chat/FollowupChips';
import { ChatConditionalSurfaces } from '@/components/chat/ChatConditionalSurfaces';
import { EyesWidget } from '@/components/eyes/EyesWidget';
import { useEyesChatWiring } from '@/components/eyes/useEyesChatWiring';
import { SelectionActions } from '@/components/chat/SelectionActions';
import { ResetConversationConfirm } from '@/components/chat/ResetConversationConfirm';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { FeatureErrorBoundary } from '@/components/errors';

import { useDebugPanelEnabled } from '@/hooks/useDebugPanelEnabled';
import { useAppConfig, type AppConfig } from '@/hooks/useAppConfig';
import { BookmarkStateProvider } from '@/lib/bookmark-state-context';
import { PeersAvailabilityProvider } from '@/lib/peers/availability-context';
import { EmailShareAvailabilityProvider } from '@/lib/email-share/availability-context';
import { emailShareAvailable } from '@/lib/email-share/share';
import { peersAvailable } from '@/lib/peers/image-share';
import { useInputDraft } from '@/hooks/useInputDraft';
import { useCardComposition, cardCompositionDisabled } from '@/hooks/useCardComposition';
import { CardCompositionChip } from '@/components/chat/CardCompositionChip';
import { useSkills } from '@/hooks/useSkills';
import {
  buildStaticSlashCommands,
  userShortcutCommands,
  type SlashCommand,
} from '@/lib/slash-commands';
import { runLocalCommand } from '@/lib/chat-local-commands';
import { useChatShortcuts } from '@/hooks/useChatShortcuts';
import { useChatSuggestions } from '@/hooks/useChatSuggestions';
import { useAutoSendIntent } from '@/hooks/useAutoSendIntent';
import { useDeepLinkParams } from '@/hooks/useDeepLinkParams';
import { resolveInitialMessage } from '@/lib/chat-initial-message';
import type { CapabilityDirectiveWire } from '@/types/directive';
import { useUsageLimits } from '@/hooks/useUsageLimits';
import { UsageBanners } from '@/components/usage/UsageBanners';
import { ActiveCallBanner } from '@/components/telephony/ActiveCallBanner';
import { LiveBanner } from '@/components/live/LiveBanner';
import { useLiveChatBindings } from '@/components/live/useLiveChatBindings';
import { useLiveSession } from '@/hooks/useLiveSession';
import { useLiveHoldsMicrophone } from '@/stores/liveStore';
import { ActiveSpacesIndicator } from '@/components/spaces/ActiveSpacesIndicator';
import { isLanguage, fallbackLng, type Language } from '@/i18n/settings';

/** Short locale of an i18n language tag ("fr-FR" → "fr"; default "fr"). */
function shortLang(language: string | undefined): Language {
  const short = (language || fallbackLng).split('-')[0];
  return isLanguage(short) ? short : fallbackLng;
}

/**
 * The composer's instance flags (module-level — CC discipline): attachments
 * default ON (the historical behaviour), meeting recording default OFF
 * (ADR-258: an instance that does not publish the flag has no recorder),
 * the knowledge-space documents in the « + » default OFF (no spaces, no
 * documents to offer).
 */
function composerFeatureFlags(config: AppConfig | null): {
  attachmentsEnabled: boolean;
  knowledgeDocumentsEnabled: boolean;
  meetingsEnabled: boolean;
} {
  return {
    attachmentsEnabled: config?.features?.attachments_enabled ?? true,
    knowledgeDocumentsEnabled: config?.features?.rag_spaces_enabled ?? false,
    meetingsEnabled: config?.features?.meetings_enabled ?? false,
  };
}

/**
 * What locks the composer and the voice badge (module-level — CC discipline):
 * a running turn, the quota wall, and — ADR-299 — a live session, which owns
 * the microphone and the turn (the person speaks; the composer says why it is
 * closed). `apiUsable` is what the composer's own availability line reads.
 */
function composerLocks(flags: {
  apiAvailable: boolean;
  isTyping: boolean;
  isUsageBlocked: boolean;
  liveOpen: boolean;
}): { input: boolean; voice: boolean; apiUsable: boolean; reasonKey: string | null } {
  const { apiAvailable, isTyping, isUsageBlocked, liveOpen } = flags;
  return {
    input: isTyping || isUsageBlocked || liveOpen,
    voice: !apiAvailable || isTyping || isUsageBlocked || liveOpen,
    apiUsable: apiAvailable && !isUsageBlocked,
    reasonKey: liveOpen ? 'live.composer_locked' : null,
  };
}

/**
 * Whether the bubbles may offer the bookmark toggle (module-level — CC
 * discipline): default OFF, an instance that does not publish the flag keeps
 * no answers (ADR-282).
 */
function bookmarksEnabled(config: AppConfig | null): boolean {
  return config?.features?.bookmarks_enabled ?? false;
}

/**
 * Whether the grounded starter rail can be shown — and therefore fetched.
 *
 * Module-level and pure (CC discipline: the page's render function is under a
 * shrink-only complexity ratchet). A busy chat must not pay for a rail nobody
 * will read, and "no messages yet" is only meaningful once the history has
 * SETTLED — an empty list mid-load is not an empty conversation.
 */
function canShowGroundedRail(args: {
  authReady: boolean;
  historySettled: boolean;
  messageCount: number;
}): boolean {
  return args.authReady && args.historySettled && args.messageCount === 0;
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
  const { initialDraft, initialComposition, saveDraft } = useInputDraft(user);

  // QW-9 / UXR Lot 2 (A7) / N-13 / QW-24 (ADR-173) / ADR-210: the one-shot
  // deep links, read live and cleared through the History API. The four rules
  // and the production defects that paid for them are documented in the hook.
  const { spotlightVoice, pendingIntent, pendingDirective, replayedIntent, clearIntent } =
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
    chatStatus, // Raw FSM status — the expressive-eyes widget needs the distinction
    activeStreamId, // Assistant message currently streaming (steps/caret styling)
    streamPhase, // 'progress' (execution steps) vs 'answer' (real tokens)
    isConnected,
    apiAvailable,
    conversationTotals: sessionTotals, // Totals accumulated during the current session (SSE done chunks)
    registry, // LARS: registry items for rich rendering (MCP Apps, etc.)
    sendMessage,
    setMessages,
    appendMessage,
    mergeServerPage,
    clearMessages,
    currentDebugMetrics, // Debug Panel: Scoring metrics for current request
    debugMetricsHistory, // Debug Panel: Cumulative history of all request metrics
    browserScreenshot, // Browser Screenshots: Current overlay data
    contextUsage, // Context-usage pill: tokens vs compaction threshold
    hydrateContextUsage, // Seeds the pill from /me/totals on page load
    checkAndResumeActiveRun, // ADR-117 Lot 2: silent reattach to an in-flight run
    stopGeneration, // ADR-117 Lot 3: stop button (cancels the in-flight run)
    stopVoice, // ADR-329: her phrase or the stop word cuts LIA's voice
    hitl, // HITL approval card state (Lot 1 P1-V1)
    submitHitlDecision, // One-click approval (structured decision, classifier bypassed)
    hydratePendingHitl, // Card rehydration after reload (GET /agents/hitl/pending)
    connectorNotices, // Connector error banners (Lot 3 P3, ADR-134)
    dismissConnectorNotice,
  } = useChat({ debugPanelVisible: showDebugPanel });

  // Blink the tab title while LIA works and the tab is in the background (I5)
  useLiveTabTitle(isTyping);

  // Live mode (ADR-299): the session speaks to the chat through its own
  // doors, and locks the composer while it holds the microphone.
  const liveBindings = useLiveChatBindings({
    messages,
    hitl,
    sendMessage,
    appendMessage,
    stopGeneration,
  });
  const liveSession = useLiveSession(liveBindings);
  const liveOpen = useLiveHoldsMicrophone();
  const locks = composerLocks({ apiAvailable, isTyping, isUsageBlocked, liveOpen });

  const {
    loadConversationPage,
    loadOlderMessages,
    readNewestPage,
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
  const initialComposerMessage = resolveInitialMessage(searchParams, initialDraft, replayedIntent);
  const cardComposition = useCardComposition({
    initialMessage: initialComposerMessage,
    initialComposition,
    saveDraft,
    disabled: cardCompositionDisabled(locks, hitlAwaitsUser(hitl.status)),
  });
  const { onTextChange } = cardComposition;
  const [currentMessage, setCurrentMessage] = useState(() => initialComposerMessage ?? '');

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

  // Expressive eyes: per-turn signal wiring (new turn, post-response reaction,
  // typing activity, notification pings). Lives in its own hook — the page's
  // render function sits under the complexity ratchet.
  const eyesWiring = useEyesChatWiring(chatStatus, messages);

  // Handle message change from ChatInput (geolocation prompt detection +
  // draft persistence — debounced, empty clears immediately).
  const handleMessageChange = useCallback(
    (message: string) => {
      setCurrentMessage(message);
      onTextChange(message);
      eyesWiring.onTyping(message);
    },
    [onTextChange, eyesWiring]
  );

  // Totals from API (loaded at startup from message_token_summary)
  // These totals are the source of truth for persisted history
  const [apiTotals, setApiTotals] = useState<ConversationTotals | null>(null);

  // The node, just above the sticky composer, where the list draws its floating
  // return button: sticky at the list's own bottom it sat UNDER the composer.
  const [scrollUiSlot, setScrollUiSlot] = useState<HTMLDivElement | null>(null);

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

  // ADR-320: the thread follows the server without ever being reloaded —
  // notifications keep their toast, and every message that lands elsewhere
  // is MERGED into the thread once it is free (hooks/useChatServerSync).
  useChatServerSync({
    signedIn: !!user,
    authLoading: isLoading,
    apiAvailable,
    isTyping,
    historyView,
    isLoadingOlder,
    messages,
    readNewestPage,
    mergeServerPage,
    clearMessages,
    setApiTotals,
    setHasMoreOlder,
    setOldestCursor,
    onNotification: eyesWiring.onNotification,
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

  const sendComposerMessage = useCallback(
    (...args: Parameters<typeof sendMessage>) =>
      sendMessageFromPresent(
        args[0],
        args[1],
        args[2],
        args[3],
        args[4],
        args[5],
        args[6],
        cardComposition.composition?.selection
      ),
    [sendMessageFromPresent, cardComposition.composition]
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
    (prompt: string, selection?: import('@/types/card-actions').CardCompositionWire) => {
      void sendMessageFromPresent(
        prompt,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        selection
      );
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
  const { suggestions: groundedSuggestions } = useChatSuggestions(
    canShowGroundedRail({ authReady, historySettled, messageCount: messages.length })
  );
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
  // The id → side-effect mapping lives in `lib/chat-local-commands` (a table
  // whose agreement with the registry is asserted in BOTH directions), so a
  // command added to the menu and forgotten here fails CI instead of shipping
  // as an entry that does nothing when pressed.
  const handleLocalCommand = useCallback(
    (commandId: string) => {
      runLocalCommand(commandId, {
        navigate: path => router.push(path),
        openSearch: () => {
          // Mobile: the search row auto-focuses itself on mount. Desktop: the
          // header input is already mounted — focus it via its OWN marker
          // (a bare input[type=search] selector could catch a foreign field).
          setMobileSearchOpen(true);
          requestAnimationFrame(() => {
            document.querySelector<HTMLElement>('input[data-chat-search]')?.focus();
          });
        },
      });
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
  const followupMotivation = useMemo(
    () => visibleMotivation(messages, isTyping || !!activeStreamId || historyView),
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
  const chipPrefill = cardComposition.prefill;
  const handleFollowupPick = cardComposition.prefillText;

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

  // Foreground return (ADR-117 Lot 2): the OS may have dropped the run's
  // stream while backgrounded — if the run is still going, silently
  // reattach. What else arrived meanwhile is merged by the sync, which asks
  // on its own on this same return (ADR-320); comparing page LENGTHS here
  // missed every message once 50 were loaded.
  const isReloadingRef = useRef(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleVisibilityChange = async () => {
      // Guard: only when visible, authenticated, not typing, not already running
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
        const resumed = await checkAndResumeActiveRun();
        if (resumed) {
          // A connection dropped mid-stream may have left a stale partial
          // bubble + error bubble behind — replace with DB truth so the
          // resumed bubble isn't duplicated. The reducer's SET_MESSAGES
          // anti-race guard preserves the resuming bubble itself. A failed
          // read THROWS (caught below): an empty page must never replace
          // the thread.
          const page = await readNewestPage();
          setMessages(page.messages);
          setHasMoreOlder(page.hasMore);
          setOldestCursor(page.nextCursor);
        }
      } catch (error) {
        logger.warn('Failed to resume the run on visibility change', {
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
  }, [user, apiAvailable, isTyping, readNewestPage, setMessages, checkAndResumeActiveRun]);

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
          <p className="text-px-13 mobile:text-sm text-muted-foreground">
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
          the dashboard layout may insert ABOVE this shell, and
          `--meeting-banner-h` the height of the sticky recording banner
          (ADR-259) and `--radio-banner-h` the radio's bar under it (ADR-324),
          both placed above the page content; each defaults to 0px,
          so this arithmetic is unchanged whenever no banner is mounted. Without
          it, a broken connector would push the composer below the fold — the
          constant above cannot know about a block added after it was written. */}
      <div className="flex h-[calc(100vh-5.25rem-var(--connector-banner-h,0px)-var(--meeting-banner-h,0px)-var(--radio-banner-h,0px))] supports-[height:100dvh]:h-[calc(100dvh-5.25rem-var(--connector-banner-h,0px)-var(--meeting-banner-h,0px)-var(--radio-banner-h,0px))] gap-4">
        {/* Main Chat Area: a LIGHT frosted glass over the page's cosmos
            (AppCosmos), seen between the bubbles (owner, 2026-10-03). The
            header, the composer and the bubbles keep their own surfaces; the
            panel's `backdrop-filter` makes it their backdrop root, so the
            header's and composer's glass still frost the bubbles passing
            beneath them, as before. */}
        <div className="flex flex-col flex-1 min-w-0 rounded-xl border border-border/50 bg-background/35 shadow-lg backdrop-blur-md overflow-hidden">
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
                `shrink-0` middle: the middle (hands-free, context, spaces) is CENTRED when
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
                        <span className="text-px-11 mobile:text-xs font-semibold text-rose-700 dark:text-rose-300">
                          {t('chat.input.status.offline')}
                        </span>
                      </div>
                    ) : null}
                    {/* The amber "processing…" pill used to sit here — removed
                    2026-08-20: the expressive eyes carry that state now, and
                    richer (thinking vs searching vs answering). Offline stays:
                    it is actionable information the eyes do not carry. */}
                    {/* Mobile search toggle (< 880px) — unfolds the input row in
                    the ChatSearchBar below the header (QW-2). */}
                    {/* data-eyes-anchor-start sits on BOTH search forms — the
                    eyes widget docks from the first VISIBLE one, so the
                    default spot follows the responsive breakpoint. */}
                    <button
                      type="button"
                      onClick={() => setMobileSearchOpen(open => !open)}
                      aria-expanded={mobileSearchOpen}
                      aria-label={t('chat.search.open_mobile')}
                      data-eyes-anchor-start
                      className="mobile:hidden p-2 rounded-full hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <Search className="h-4 w-4 text-muted-foreground" aria-hidden />
                    </button>
                    {/* Search input (≥ 880px) — filters currently loaded messages
                    by content; left-aligned in the header. 12rem when the side
                    has it, narrower when it does not: a fixed-width field in a
                    shrinking side overflowed onto the centre group at 880 px
                    with an enlarged text size (font-size-extremes.spec.ts). */}
                    <div
                      className="relative hidden min-w-0 mobile:flex items-center"
                      data-eyes-anchor-start
                    >
                      <Search className="absolute left-2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
                      <input
                        type="search"
                        data-chat-search
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        placeholder={t('conversations.search_placeholder')}
                        aria-label={t('conversations.search_placeholder')}
                        className="h-8 w-48 max-w-full pl-7 pr-7 text-xs rounded-full bg-background border border-border focus:outline-none focus:ring-1 focus:ring-ring"
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

                  {/* Centre (in flow, shrink-0), in the owner's order
                  (2026-10-01): the hands-free badge — single instance, always
                  mounted AND always shown (greyed while off, a tap turns it
                  on) to preserve KWS state —, the context-usage pill, then the
                  active-spaces pill. The context pill (owner arbitration
                  2026-08-05: observation it may be, it earns its place at
                  EVERY width — it was `hidden` below `mobile` on the right
                  side and users missed it; its ~52 px fit a 360 px row, and
                  tap toggles the tooltip touch-side) stays hidden until the
                  first turn completes (no data yet); conversation totals ride
                  its tooltip (QW-12). `shrink-0` keeps the group intact while
                  the flex-1 sides absorb the width; equal sides keep it
                  visually centred and let it SHIFT rather than overlap when a
                  side grows. data-eyes-anchor-end sits on the GROUP: the eyes
                  dock between the search field and its first control, which
                  they must never cover, whatever the group holds. Below `sm`
                  the three pills and their gap tighten (px-2, gap-1.5): with
                  the hands-free badge always shown, a 320 px row needs those
                  pixels or the last pill slides under « Delete » (measured). */}
                  <div className="flex shrink-0 items-center gap-1.5 sm:gap-2" data-eyes-anchor-end>
                    <VoiceModeBadge
                      onTranscription={(text, meta) =>
                        sendMessageFromPresent(text, undefined, undefined, meta)
                      }
                      onInterrupt={stopVoice}
                      disabled={locks.voice}
                    />
                    {/* ADR-299 (wave 2, A1): the entry into the live mode is the
                        header's voice menu; the session it opens lives HERE, with
                        the chat's doors (`useLiveSession` consumes the start). */}
                    {contextUsage && (
                      <ContextUsagePill
                        usage={contextUsage}
                        totals={
                          user?.tokens_display_enabled &&
                          (combinedTotals.tokensIn > 0 || combinedTotals.tokensOut > 0)
                            ? { ...combinedTotals, userMessageCount }
                            : null
                        }
                      />
                    )}
                    <ActiveSpacesIndicator />
                  </div>

                  {/* Right side: Delete/New chat, in flow. `min-w-0 flex-1`
                  mirrors the left side so the centre stays centred;
                  `justify-end` keeps it pinned to the right edge. */}
                  <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
                    {/* Delete/New chat button. Below `sm` the label steps aside —
                    the row cannot carry it next to the centre group — so
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
                      <span className="hidden sm:inline text-px-11 mobile:text-xs font-semibold text-rose-700 dark:text-rose-300">
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
              {/* ADR-299: « you are talking with LIA » — Stop cancels LIA's
                  turn AND ends the session, the one door that kills a turn. */}
              <LiveBanner
                session={liveSession}
                onStopAll={() => {
                  void stopGeneration();
                  void liveSession.end('ended');
                }}
              />
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
                <BookmarkStateProvider enabled={bookmarksEnabled(appConfig)}>
                  <PeersAvailabilityProvider available={peersAvailable(appConfig)}>
                    <EmailShareAvailabilityProvider available={emailShareAvailable(appConfig)}>
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
                        scrollUiSlot={scrollUiSlot}
                        onRetry={handleRetry}
                        onPrefillComposer={handleFollowupPick}
                        onCardCompose={cardComposition.onAvailableCompose}
                        // W8: an empty chat offers three ways in. Same rail as the
                        // follow-up chips — it prefills the composer, never sends.
                        onStarterPick={handleFollowupPick}
                        groundedSuggestions={groundedSuggestions}
                      />
                    </EmailShareAvailabilityProvider>
                  </PeersAvailabilityProvider>
                </BookmarkStateProvider>
              </div>
            </RegistryProvider>

            {/* Frosted-glass footer, STICKY INSIDE the same scroll container as
                the header (owner request 2026-07-30). The material only reads
                as glass when something passes behind it, and as a sibling below
                the scroll area nothing ever did — the exact reason the header
                was moved in here. Same tokens as the header, so the two edges
                of the thread are one material. */}
            <div className="sticky bottom-0 z-20">
              {/* The floating return button's place: right above the footer,
                  whatever its height (a multi-line draft, the surfaces above
                  the composer), and above it in the stacking order. */}
              <div
                ref={setScrollUiSlot}
                className="pointer-events-none absolute inset-x-0 bottom-full flex justify-center pb-2"
              />
              {/* Conditional surfaces between the thread and the composer, gated by
                  the S1 arbiter. Extracted as one element on purpose: four inline
                  branches here would grow this render hotspot past its complexity
                  cap, and the band is a subject of its own. */}
              <ChatConditionalSurfaces
                surfaces={chatSurfaces}
                followupSuggestions={followupSuggestions}
                followupMotivation={followupMotivation}
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
                  initialMessage={initialComposerMessage}
                  compositionContext={
                    <CardCompositionChip
                      composition={cardComposition.composition}
                      onRemove={cardComposition.removeComposition}
                    />
                  }
                  sentHistory={sentHistory}
                  prefill={chipPrefill}
                  slashCommands={slashCommands}
                  onLocalCommand={handleLocalCommand}
                  spotlightVoice={spotlightVoice}
                  onSendMessage={sendComposerMessage}
                  disabled={locks.input}
                  disabledReasonKey={locks.reasonKey}
                  isConnected={isConnected}
                  apiAvailable={locks.apiUsable}
                  onMessageChange={handleMessageChange}
                  {...composerFeatureFlags(appConfig)}
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
        {cardComposition.confirmDialog}

        {/* Expressive eyes — floating, draggable, hideable (restore dot). */}
        <EyesWidget
          chatStatus={chatStatus}
          streamPhase={streamPhase}
          hitlAwaiting={hitl.status === 'awaiting'}
        />

        {/* Debug Panel - Right side (only when enabled + desktop viewport ≥1024px),
            at the width the person dragged it to — into the conversation, which
            keeps its floor and takes whatever room is left (`min-w-0`). */}
        {showDebugPanel && (
          <ResizableDebugPanel>
            <DebugPanel
              lng={lng}
              key={latestDebugMetrics ? 'has-metrics' : 'no-metrics'}
              metrics={latestDebugMetrics}
              history={debugMetricsHistory}
              className="h-full"
            />
          </ResizableDebugPanel>
        )}
      </div>
    </FeatureErrorBoundary>
  );
}

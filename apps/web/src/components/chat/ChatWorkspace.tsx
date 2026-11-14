'use client';

import { useMediaQuery } from '@/hooks/useMediaQuery';

import { useAuth } from '@/hooks/useAuth';
import { useConversation } from '@/hooks/useConversation';
import { useDiscussionUsage } from '@/hooks/useDiscussionUsage';
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
import { ChatSearchBar } from '@/components/chat/search/ChatSearchBar';
import { useChatHistorySearch } from '@/hooks/useChatHistorySearch';
import { DebugPanel } from '@/components/debug/DebugPanel';
import { ResizableDebugPanel } from '@/components/debug/ResizableDebugPanel';
import { useDebugMetrics } from '@/components/debug/hooks/useDebugMetrics';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { discussionReach } from '@/lib/discussion-leave';
import { logger } from '@/lib/logger';
import { sentHistoryOf } from '@/lib/sent-history';
import {
  chatListActivity,
  hitlAwaitsUser,
  surfaceIsBusy,
  visibleChatSurfaces,
} from '@/lib/chat-surfaces';
import { visibleFollowups, visibleMotivation } from '@/components/chat/FollowupChips';
import { useChatProposal } from '@/hooks/useChatProposal';
import { ChatConditionalSurfaces } from '@/components/chat/ChatConditionalSurfaces';
import { useAuthenticatedEyesChatState } from '@/components/eyes/useEyesChatState';
import { useEyesChatWiring } from '@/components/eyes/useEyesChatWiring';
import {
  ChatDiscussionHost,
  type ChatDiscussionViewProps,
} from '@/components/chat/ChatDiscussionHost';
import { ChatWorkspaceToolbar } from '@/components/chat/ChatWorkspaceToolbar';
import { DiscussionReset } from '@/components/chat/DiscussionReset';
import { Button } from '@/components/ui/button';
import { getApiErrorStatus } from '@/lib/api-error';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { FeatureErrorBoundary } from '@/components/errors';
import { stopAvatarCommentsForChatFailure } from '@/lib/avatars/runtime';

import { useDebugPanelEnabled } from '@/hooks/useDebugPanelEnabled';
import { useAppConfig } from '@/hooks/useAppConfig';
import { capabilityAvailable } from '@/lib/capability-availability';
import { composerFeatureFlags } from '@/lib/chat-composer-capabilities';
import { BookmarkStateProvider } from '@/lib/bookmark-state-context';
import { bookmarkKeepingAvailable, bookmarksReadable } from '@/lib/bookmarks/availability';
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
import { resolveInitialComposition, resolveInitialMessage } from '@/lib/chat-initial-message';
import type { CapabilityDirectiveWire } from '@/types/directive';
import { useUsageLimits } from '@/hooks/useUsageLimits';
import { UsageBanners } from '@/components/usage/UsageBanners';
import { WaitingMessageSlot } from '@/components/chat/WaitingMessageBubble';
import { useWaitingComposer } from '@/hooks/useWaitingComposer';
import type { SendExtras } from '@/lib/waiting-message';
import type { UseChatReturn } from '@/hooks/useChat';
import { ActiveCallBanner } from '@/components/telephony/ActiveCallBanner';
import { LiveBanner } from '@/components/live/LiveBanner';
import { useLiveHoldsMicrophone } from '@/stores/liveStore';
import { isLanguage, fallbackLng, type Language } from '@/i18n/settings';

function resetAvailable(apiAvailable: boolean, isTyping: boolean): boolean {
  return apiAvailable && !isTyping;
}

/** Short locale of an i18n language tag ("fr-FR" → "fr"; default "fr"). */
function shortLang(language: string | undefined): Language {
  const short = (language || fallbackLng).split('-')[0];
  return isLanguage(short) ? short : fallbackLng;
}

/**
 * What locks the composer and the voice badge (module-level — CC discipline):
 * the quota wall and — ADR-299 — a live session, which owns the microphone and
 * the turn (the person speaks; the composer says why it is closed). A running
 * turn no longer closes the text: words typed meanwhile wait for their turn
 * (ADR-384); it still closes the voice and a card composition, which only a
 * live request can carry. `apiUsable` is what the composer's own availability
 * line reads.
 */
export function composerLocks(flags: {
  apiAvailable: boolean;
  isTyping: boolean;
  isUsageBlocked: boolean;
  liveOpen: boolean;
  waitingForHistory: boolean;
}): {
  input: boolean;
  voice: boolean;
  composition: boolean;
  apiUsable: boolean;
  reasonKey: string | null;
} {
  const { apiAvailable, isTyping, isUsageBlocked, liveOpen, waitingForHistory } = flags;
  const input = isUsageBlocked || liveOpen || waitingForHistory;
  return {
    input,
    composition: input || isTyping,
    voice: !apiAvailable || isTyping || isUsageBlocked || liveOpen || waitingForHistory,
    apiUsable: apiAvailable && !isUsageBlocked,
    reasonKey: liveOpen ? 'live.composer_locked' : null,
  };
}

/**
 * What a composer send carries beyond its words (module-level — CC
 * discipline): anything here keeps the live request (ADR-384).
 */
function sendExtrasOf(
  args: Parameters<UseChatReturn['sendMessage']>,
  composition: unknown
): SendExtras {
  return {
    attachmentIds: args[1],
    sttProvider: args[3]?.stt_provider,
    hitlDecision: args[4],
    directive: args[5],
    live: args[6],
    composition,
  };
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

export function ChatWorkspace(props: { embedded?: boolean; openingDraft?: string }) {
  const { user, isLoading } = useAuth();
  const { t } = useTranslation();
  const router = useLocalizedRouter();
  const { isEnabled: debugPanelEnabled } = useDebugPanelEnabled();
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const { config: appConfig, loading: configLoading } = useAppConfig(
    Boolean(user?.is_active) && !isLoading
  );
  useEffect(() => {
    if (!isLoading && user && !user.is_active) router.push('/dashboard');
  }, [user, isLoading, router]);

  if (isLoading || (configLoading && !appConfig)) {
    return (
      <p role="status" className="flex items-center justify-center gap-2 p-4 text-sm">
        <LoadingSpinner aria-hidden="true" />
        {t('chat.loading_conversation')}
      </p>
    );
  }
  if (!user?.is_active) return null;
  return (
    <ChatDiscussionHost
      key={user.id}
      ownerId={user.id}
      {...props}
      appConfig={appConfig}
      showDebugPanel={debugPanelEnabled && isDesktop}
      View={ChatWorkspaceView}
    />
  );
}

function ChatWorkspaceView({
  embedded,
  openingDraft,
  appConfig,
  showDebugPanel,
  chat,
  target,
  selection,
  uploads,
  switcher,
  live,
  cleanup,
  refreshTarget,
  refreshCatalogue,
  openDiscussion,
  reset,
  consumeOpeningDraft,
  recoverOnDraftRelease,
}: ChatDiscussionViewProps) {
  const { user, isLoading } = useAuth();
  const searchParams = useSearchParams();
  const authReady = Boolean(user) && !isLoading;

  // Usage limits (per-user quotas)
  const {
    isBlocked: isUsageBlocked,
    blockReason: usageBlockReason,
    limits: usageLimits,
  } = useUsageLimits();

  const { initialDraft, initialComposition, saveDraft } = useInputDraft(
    user,
    true,
    target ?? undefined,
    recoverOnDraftRelease
  );
  useEffect(() => {
    if (openingDraft === undefined) return;
    saveDraft(openingDraft);
    consumeOpeningDraft();
  }, [openingDraft, saveDraft, consumeOpeningDraft]);

  // QW-9 / UXR Lot 2 (A7) / N-13 / QW-24 (ADR-173) / ADR-210: the one-shot
  // deep links, read live and cleared through the History API. The four rules
  // and the production defects that paid for them are documented in the hook.
  const { spotlightVoice, pendingIntent, pendingDirective, replayedIntent, clearIntent } =
    useDeepLinkParams(saveDraft, !embedded);

  // One-shot requests wait until this exact generation has loaded.
  const [historyState, setHistoryState] = useState<'loading' | 'ready' | 'failed'>('loading');
  const [historyAttempt, setHistoryAttempt] = useState(0);
  const historySettled = historyState === 'ready';

  const {
    messages,
    isTyping,
    chatStatus, // Raw FSM status — the expressive-eyes widget needs the distinction
    activeStreamId, // Assistant message currently streaming (steps/caret styling)
    streamPhase, // 'progress' (execution steps) vs 'answer' (real tokens)
    isConnected,
    apiAvailable,
    registry, // LARS: registry items for rich rendering (MCP Apps, etc.)
    sendMessage,
    setMessages,
    mergeServerPage,
    clearMessages,
    currentDebugMetrics, // Debug Panel: Scoring metrics for current request
    debugMetricsHistory, // Debug Panel: Cumulative history of all request metrics
    browserScreenshot, // Browser Screenshots: Current overlay data
    contextUsage, // Context-usage pill: tokens vs compaction threshold
    hydrateContextUsage, // Seeds the pill from /me/totals on page load
    checkAndResumeActiveRun, // ADR-117 Lot 2: silent reattach to an in-flight run
    resumeActiveRun, // ADR-384: join the run that sends a waiting message
    runStreamId, // ADR-384: the run words typed meanwhile wait behind
    registerBusyRefusal, // ADR-384: a send refused by a busy account waits
    stopGeneration, // ADR-117 Lot 3: stop button (cancels the in-flight run)
    stopVoice, // ADR-329: her phrase or the stop word cuts LIA's voice
    hitl, // HITL approval card state (Lot 1 P1-V1)
    submitHitlDecision, // One-click approval (structured decision, classifier bypassed)
    hydratePendingHitl, // Card rehydration after reload (GET /agents/hitl/pending)
    connectorNotices, // Connector error banners (Lot 3 P3, ADR-134)
    dismissConnectorNotice,
  } = chat;

  // Blink the tab title while LIA works and the tab is in the background (I5)
  useLiveTabTitle(isTyping);

  // Live mode (ADR-299): the session speaks to the chat through its own
  // doors, and locks the composer while it holds the microphone.
  const liveOpen = useLiveHoldsMicrophone();
  const locks = composerLocks({
    apiAvailable,
    isTyping,
    isUsageBlocked,
    liveOpen,
    waitingForHistory: Boolean(selection) && !historySettled,
  });
  const resumeAlreadyRunning = useRef(isTyping);

  const {
    loadConversationPage,
    loadOlderMessages,
    readNewestPage,
    searchDiscussions,
    isLoadingOlder,
    loadConversationTotals,
    resetConversation,
  } = useConversation(selection);

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
  const initialComposerMessage = resolveInitialMessage(
    searchParams,
    initialDraft,
    replayedIntent,
    embedded,
    openingDraft
  );
  const cardComposition = useCardComposition({
    initialMessage: initialComposerMessage,
    initialComposition: resolveInitialComposition(initialComposition, embedded, openingDraft),
    saveDraft,
    disabled: cardCompositionDisabled(
      { input: locks.composition, apiUsable: locks.apiUsable },
      hitlAwaitsUser(hitl.status)
    ),
  });
  // ADR-384: words written while LIA answers wait for their turn, kept by the server.
  const waitingComposer = useWaitingComposer({
    selection,
    enabled: apiAvailable,
    busy: isTyping,
    questionPending: hitlAwaitsUser(hitl.status),
    runStreamId,
    joinRun: resumeActiveRun,
    joinRunningAnswer: checkAndResumeActiveRun,
    restoreText: cardComposition.prefillText,
  });
  const { onBusyRefusal, takes: waitingTakes } = waitingComposer;
  useEffect(() => {
    registerBusyRefusal(onBusyRefusal);
    return () => registerBusyRefusal(undefined);
  }, [registerBusyRefusal, onBusyRefusal]);
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
  useAuthenticatedEyesChatState({
    chatStatus,
    streamPhase,
    hitlAwaiting: hitl.status === 'awaiting',
  });

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
  const {
    totals: badgeTotals,
    replace: replaceBadgeTotals,
    refresh: refreshUsage,
  } = useDiscussionUsage(loadConversationTotals, isTyping, hydrateContextUsage);

  // The node, just above the sticky composer, where the list draws its floating
  // return button: sticky at the list's own bottom it sat UNDER the composer.
  const [scrollUiSlot, setScrollUiSlot] = useState<HTMLDivElement | null>(null);

  // Chat history search (QW-2): instant accent-insensitive client filter,
  // in-bubble highlight, server search across every discussion of the account
  // (lot 12) with jump-to-result, and the "history view" state. All feature
  // logic lives in the hook; how far it reaches, in `discussionReach`.
  const reach = discussionReach({
    switcher,
    current: target,
    typing: isTyping,
    open: openDiscussion,
  });
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
    hasOtherDiscussions: reach.hasOtherDiscussions,
    currentDiscussionId: reach.currentId,
    openDiscussion: reach.openResult,
    historyReady: historySettled,
    searchDiscussions,
    loadOlderMessages,
    loadConversationPage,
    setMessages,
    setHasMoreOlder,
    setOldestCursor,
  });

  // ADR-320: the thread follows the server without ever being reloaded —
  // notifications keep their toast, and every message that lands elsewhere
  // is MERGED into the thread once it is free (hooks/useChatServerSync).
  const refreshFirstMain = useCallback(() => {
    if (switcher && !selection) refreshTarget();
  }, [switcher, selection, refreshTarget]);
  useChatServerSync({
    selection,
    conversationId: target?.id,
    isMain: target?.kind !== 'secondary',
    onSelectedReset: refreshTarget,
    onCatalogueChange: refreshFirstMain,
    onMetadataChange: refreshCatalogue,
    refreshUsage,
    owner: user,
    signedIn: !!user,
    authLoading: isLoading,
    apiAvailable,
    isTyping,
    historyView,
    isLoadingOlder,
    messages,
    readNewestPage,
    hydratePendingHitl,
    mergeServerPage,
    clearMessages,
    setApiTotals: replaceBadgeTotals,
    setHasMoreOlder,
    setOldestCursor,
    onNotification: eyesWiring.onNotification,
    onThreadSignal: waitingComposer.onThreadSignal,
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
    async (...args: Parameters<typeof sendMessage>) => {
      const composition = cardComposition.composition?.selection;
      if (waitingTakes(args[0], sendExtrasOf(args, composition))) return;
      return sendMessageFromPresent(
        args[0],
        args[1],
        args[2],
        args[3],
        args[4],
        args[5],
        args[6],
        composition
      );
    },
    [sendMessageFromPresent, cardComposition.composition, waitingTakes]
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
    isTyping: isTyping || liveOpen,
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
  // Asked only where the instance offers the skills: their router refuses
  // every route under the operator's switch (ADR-280).
  const { skills } = useSkills(false, capabilityAvailable(appConfig, 'skills'));
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
  const surfaceBusy = surfaceIsBusy({ isTyping, activeStreamId, historyView });
  const followupSuggestions = useMemo(
    () => visibleFollowups(messages, surfaceBusy),
    [messages, surfaceBusy]
  );
  const followupMotivation = useMemo(
    () => visibleMotivation(messages, surfaceBusy),
    [messages, surfaceBusy]
  );
  // ADR-375: the habit proposal the latest answer shows, decided through the
  // inbox's own door.
  const { proposal: habitProposal, decisions: proposalDecisions } = useChatProposal(
    messages,
    surfaceBusy,
    lng
  );
  const hasHabitProposal = habitProposal !== null;

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
        hasProposal: hasHabitProposal,
        hasFollowups: followupSuggestions.length > 0,
      }),
    [
      isUsageBlocked,
      hitl.status,
      connectorNotices.length,
      hasHabitProposal,
      followupSuggestions.length,
    ]
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
  }, [
    oldestCursor,
    hasMoreOlder,
    loadOlderMessages,
    setMessages,
    setHasMoreOlder,
    setOldestCursor,
  ]);

  // Parallel history and totals, then reattach only through the selected target.
  useEffect(() => {
    if (!authReady || !apiAvailable) return;
    const lifetime = new AbortController();
    void refreshUsage();
    const loadData = async () => {
      try {
        const page = await loadConversationPage();
        if (lifetime.signal.aborted) return;
        mergeServerPage(page.messages);
        setHasMoreOlder(page.hasMore);
        setOldestCursor(page.nextCursor);
        const resumed = resumeAlreadyRunning.current || (await checkAndResumeActiveRun());
        if (!resumed && !lifetime.signal.aborted) await hydratePendingHitl();
        if (!lifetime.signal.aborted) setHistoryState('ready');
      } catch (error) {
        if (lifetime.signal.aborted) return;
        const status = getApiErrorStatus(error);
        if (status === 404 || status === 409) refreshTarget();
        setHistoryState(selection ? 'failed' : 'ready');
      }
    };
    void loadData();
    return () => lifetime.abort();
  }, [
    apiAvailable,
    authReady,
    checkAndResumeActiveRun,
    historyAttempt,
    hydratePendingHitl,
    loadConversationPage,
    mergeServerPage,
    refreshTarget,
    refreshUsage,
    selection,
  ]);

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

  async function resetLegacy() {
    await resetConversation();
    clearMessages();
    saveDraft('');
    replaceBadgeTotals(null);
    setHasMoreOlder(false);
    setOldestCursor(null);
  }

  if (!user?.is_active) {
    return null;
  }

  return (
    <FeatureErrorBoundary feature="chat" onError={stopAvatarCommentsForChatFailure}>
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
      <div
        className={
          embedded
            ? 'flex h-full min-h-0 gap-4'
            : 'flex h-[calc(100vh-5.25rem-var(--connector-banner-h,0px)-var(--meeting-banner-h,0px)-var(--radio-banner-h,0px))] supports-[height:100dvh]:h-[calc(100dvh-5.25rem-var(--connector-banner-h,0px)-var(--meeting-banner-h,0px)-var(--radio-banner-h,0px))] gap-4'
        }
      >
        {/* Main Chat Area: a LIGHT frosted glass over the page's cosmos
            (AppCosmos), seen between the bubbles (owner, 2026-10-03). The
            header, the composer and the bubbles keep their own surfaces; the
            panel's `backdrop-filter` makes it their backdrop root, so the
            header's and composer's glass still frost the bubbles passing
            beneath them, as before. */}
        {/* The glass panel is a stacking context. A pending decision or browser
            transfer must lift that context above the floating companion. */}
        <div className="relative has-[[data-application-action-priority=true]]:z-40 flex flex-col flex-1 min-w-0 rounded-xl border border-border/50 bg-background/35 shadow-lg backdrop-blur-md overflow-hidden">
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
              <ChatWorkspaceToolbar
                apiAvailable={apiAvailable}
                search={{
                  value: searchQuery,
                  onChange: setSearchQuery,
                  mobileOpen: mobileSearchOpen,
                  toggleMobile: () => setMobileSearchOpen(open => !open),
                }}
                switcher={switcher}
                typing={isTyping}
                voice={{
                  onTranscription: (text, meta) =>
                    sendMessageFromPresent(text, undefined, undefined, meta),
                  onInterrupt: stopVoice,
                  disabled: locks.voice,
                }}
                context={{
                  usage: contextUsage,
                  enabled: user.tokens_display_enabled,
                  totals: badgeTotals,
                }}
                resetControl={
                  <DiscussionReset
                    target={target}
                    catalogueAvailable={Boolean(switcher)}
                    available={resetAvailable(apiAvailable, isTyping)}
                    reset={reset}
                    legacyReset={resetLegacy}
                  />
                }
              />

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
                currentDiscussionId={reach.currentId}
                canOpenOtherDiscussions={reach.openResult !== undefined}
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
              <ActiveCallBanner
                lng={lng}
                conversationTick={messages.length}
                offered={capabilityAvailable(appConfig, 'telephony')}
              />
              {/* ADR-299: « you are talking with LIA » — Stop cancels LIA's
                  turn AND ends the session, the one door that kills a turn. */}
              <LiveBanner {...live} />
              {cleanup}
              {historyState === 'failed' && (
                <div
                  role="alert"
                  className="flex flex-wrap items-center justify-center gap-2 border-b bg-card p-2 text-sm"
                >
                  <span>{t('chat.discussions.history_error')}</span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setHistoryState('loading');
                      setHistoryAttempt(attempt => attempt + 1);
                    }}
                  >
                    {t('common.retry')}
                  </Button>
                </div>
              )}
              <UsageBanners
                limits={usageLimits}
                isBlocked={isUsageBlocked}
                blockReason={usageBlockReason}
              />
            </div>

            <RegistryProvider value={registryWithHistory}>
              {/* Headless: celebrates relationship-stage milestones (I7) */}
              <PsycheMilestoneWatcher />
              {/* `grow shrink-0`: takes the leftover height when the thread is
                  short (which keeps the sticky composer at the bottom), and
                  keeps its own content height when it is long (`shrink-0`, or
                  a flex item would compress and clip the messages). */}
              <div className="flex grow shrink-0 flex-col">
                <BookmarkStateProvider
                  enabled={bookmarksReadable(appConfig)}
                  canKeep={bookmarkKeepingAvailable(appConfig)}
                >
                  <PeersAvailabilityProvider available={peersAvailable(appConfig)}>
                    <EmailShareAvailabilityProvider available={emailShareAvailable(appConfig)}>
                      <ChatMessageList
                        messages={displayedMessages}
                        psycheOffered={capabilityAvailable(appConfig, 'psyche')}
                        {...chatListActivity(searchQuery, {
                          isTyping,
                          activeStreamId,
                          hasMoreOlder,
                        })}
                        streamPhase={streamPhase}
                        browserScreenshot={browserScreenshot}
                        // Scroll-up pagination — disabled while the user is searching
                        // (search filters client-side over already-loaded messages
                        // only, so a sentinel would conflate "no match in this page"
                        // with "more remote history exists").
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
            <div className="lia-chat-footer sticky bottom-0 z-20">
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
              <WaitingMessageSlot bubble={waitingComposer.bubble} />
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
                habitProposal={habitProposal}
                proposalDecisions={proposalDecisions}
              />

              {/* No background here: `ChatInput` owns the glass material (its
                  own root used to paint an opaque `bg-card` over anything set
                  at this level). This wrapper is positioning only. */}
              <div className="shadow-sm">
                <ChatInput
                  uploadDraft={uploads}
                  observeAttachmentLink={!embedded}
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
                  {...composerFeatureFlags(appConfig, { textOnly: isTyping })}
                  isGenerating={isTyping}
                  onStopGeneration={stopGeneration}
                />
              </div>
            </div>
          </div>
        </div>

        {cardComposition.confirmDialog}

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

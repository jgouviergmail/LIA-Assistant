import { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState } from 'react';
import { Message, BrowserScreenshotData } from '@/types/chat';
import type { StreamPhase } from '@/types/chat-state';
import { ChatMessage } from './ChatMessage';
import { BrowserScreenshotOverlay } from './BrowserScreenshotOverlay';
import { ScrollToBottomButton } from './ScrollToBottomButton';
import { TypingIndicator } from './TypingIndicator';
import { AnimatedEmoji } from '@/components/ui/animated-emoji';
import { MessageSquare } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { usePsyche } from '@/hooks/usePsyche';
import {
  SCROLL_UI_INITIAL,
  decideFollow,
  distanceToBottom,
  isScrollerAtBottom,
  pinToBottom,
  scrollUiReducer,
  type ScrollUiState,
} from '@/lib/chat-scroll';
import { logger } from '@/lib/logger';
import { composeStarterRail } from '@/lib/chat-starters';
import type { ChatSuggestion } from '@/hooks/useChatSuggestions';
import { cn } from '@/lib/utils';

export interface ChatMessageListProps {
  messages: Message[];
  isTyping?: boolean;
  /** Id of the assistant message currently receiving stream updates (null when idle). */
  activeStreamId?: string | null;
  /** 'progress' (execution steps) vs 'answer' (real tokens) — drives step/caret styling. */
  streamPhase?: StreamPhase;
  browserScreenshot?: BrowserScreenshotData | null;
  /** When true, the scroll-up sentinel is rendered and triggers ``onLoadOlder``
   *  as soon as it enters the viewport. */
  hasMoreOlder?: boolean;
  /** Renders the inline loader at the top while older messages are fetched. */
  isLoadingOlder?: boolean;
  /** Called when the top sentinel becomes visible. The parent owns the cursor
   *  and the state update (prepend + dedup). */
  onLoadOlder?: () => void;
  /** History-search term highlighted inside the rendered bubbles (QW-2). */
  searchHighlight?: string;
  /**
   * Replay a failed prompt (W3). Offered on the LAST error bubble only:
   * re-running an older failure would drop it into a conversation that has
   * since moved on.
   */
  onRetry?: (prompt: string) => void;
  /** Peers Lot 7: composer prefill for the peer Reply quick-action. */
  onPrefillComposer?: (text: string) => void;
  /**
   * Prefill the composer from an empty-chat starter (W8). Shares the
   * follow-up chips' rail: it fills the input, it never sends.
   */
  onStarterPick?: (text: string) => void;
  /** Grounded suggestions for the empty state (empty = generic starters). */
  groundedSuggestions?: readonly ChatSuggestion[];
  /** QW-2 history view: the floating button becomes "return to the present"
   *  and delegates to ``onReturnToPresent`` (UXR Lot 3, A3). */
  historyView?: boolean;
  /** Return-to-present handler (parent owns the page swap + in-flight guard). */
  onReturnToPresent?: () => void;
  /** Monotonic tick incremented by the page on every OWN chat send (UXR
   *  Lot 3). The EXPLICIT own-send signal for the follow decision — data
   *  diffs (last-entry role, last-user-id) both false-fired against the real
   *  engine (batched send render; post-done history reload swapping
   *  optimistic ids for server ids). */
  ownSendTick?: number;
}

export interface TimeGreeting {
  /** Emoji glyph for the empty-chat hero (AnimatedEmoji derives its codepoint). */
  glyph: string;
  /** Deep-night bucket — shows the truthful "LIA consolidates its memories" note. */
  isNight: boolean;
}

/**
 * Time-of-day greeting for the empty-chat state, in the user's local hours.
 * Deep night (23:00–05:00) shows a resting LIA — grounded in the real nightly
 * memory-consolidation jobs, stated without false precision.
 */
export function greetingForHour(hour: number): TimeGreeting {
  if (hour >= 23 || hour < 5) return { glyph: '😴', isNight: true };
  if (hour < 11) return { glyph: '☕', isNight: false }; // 05–10 morning
  if (hour < 18) return { glyph: '👋', isNight: false }; // 11–17 day
  return { glyph: '🌛', isNight: false }; // 18–22 evening
}

/**
 * Id of the last assistant message — only that row animates its psyche emoji
 * (older rows are static mood snapshots; keeps at most one looping WebP on
 * screen, spec D-5).
 */
export function getLastAssistantMessageId(messages: Message[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'assistant') {
      return messages[i].id;
    }
  }
  return null;
}

/**
 * The element that actually scrolls for a given node.
 *
 * This component renders its own `overflow-y-auto` div, but the chat page
 * wraps it in ANOTHER one (`flex-1 overflow-y-auto chat-scrollbar`) — and that
 * outer one is the real scroller. The inner div is a plain block inside it, so
 * it grows to the full content height and permanently reports
 * `scrollHeight === clientHeight`: every `scrollTop` written to it is a no-op,
 * and an IntersectionObserver rooted on it sees a viewport as tall as the whole
 * conversation, which makes the top sentinel *always* intersect.
 *
 * Resolving the real scroller from the DOM keeps the component correct whether
 * it owns the scrolling box or an ancestor does.
 */
function getScrollParent(node: HTMLElement | null): HTMLElement | null {
  let el: HTMLElement | null = node;
  while (el) {
    const overflowY = getComputedStyle(el).overflowY;
    if (
      (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') &&
      el.scrollHeight > el.clientHeight
    ) {
      return el;
    }
    el = el.parentElement;
  }
  return node;
}

/** The real scroller for a node, or null without a mounted container. */
function resolveScrollerOf(node: HTMLElement | null): HTMLElement | null {
  return node ? (getScrollParent(node) ?? node) : null;
}

/**
 * Floating return button + polite live region (UXR Lot 3). Extracted from the
 * render hotspot (CC discipline). Renders the sticky button in history view
 * (the reader is never "at the present" there — QW-2 semantics) or while the
 * reader is away; the live region announces off-screen responses.
 */
function ScrollUiOverlay({
  historyView,
  scrollUi,
  onClick,
}: {
  historyView: boolean;
  scrollUi: ScrollUiState;
  onClick: () => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      {(historyView || scrollUi.away) && (
        <div className="sticky bottom-2 z-10 flex justify-center pointer-events-none">
          <ScrollToBottomButton
            historyView={historyView}
            count={scrollUi.newWhileAway}
            onClick={onClick}
          />
        </div>
      )}
      {/* The relative wrapper is load-bearing: sr-only is position:absolute,
          and without a positioned ancestor its static position (end of the
          thread) escapes the scroller's clipping and stretches the BODY —
          the whole page grows a vertical scrollbar (QA regression). */}
      <div className="relative">
        <div aria-live="polite" className="sr-only">
          {scrollUi.newWhileAway > 0
            ? t('chat.scroll.new_responses', { count: scrollUi.newWhileAway })
            : ''}
        </div>
      </div>
    </>
  );
}

/** Id of the last list entry (null on an empty list). */
function lastIdOf(messages: Message[]): string | null {
  const last = messages[messages.length - 1];
  return last ? last.id : null;
}

/**
 * Id of the error bubble that may offer a retry (W3), or null.
 *
 * The rule is deliberately narrow: the failure must be the LAST thing in the
 * conversation, and it must have pinned a prompt.
 *
 * - Not "the most recent error anywhere": once anything follows it — a retry
 *   that worked, a new question, a proactive notification — the conversation
 *   has moved on, and replaying the old prompt would drop it into a context it
 *   was never written for.
 * - Not "any error": a proactive turn can fail with no question behind it, and
 *   there is then nothing to replay.
 *
 * Exported for its own test: this predicate is the whole placement policy.
 */
export function lastRetryableErrorId(messages: Message[]): string | null {
  const last = messages[messages.length - 1];
  if (!last || last.metadata?.type !== 'error') return null;
  return typeof last.metadata?.retryPrompt === 'string' ? last.id : null;
}

/**
 * Empty-conversation hero: time-aware greeting (☕ morning · 👋 day ·
 * 🌛 evening · 😴 deep night). AnimatedEmoji falls back to the static glyph on
 * missing asset / reduced motion; neutral day glyph until mounted (avoids the
 * SSR hydration mismatch). Extracted from the render hotspot (CC discipline).
 */
function EmptyConversation({
  mounted,
  onStarterPick,
  groundedSuggestions,
}: {
  mounted: boolean;
  onStarterPick?: (text: string) => void;
  /** Grounded suggestions for the empty state (empty = generic starters). */
  groundedSuggestions?: readonly ChatSuggestion[];
}) {
  const { t } = useTranslation();
  const greeting: TimeGreeting = mounted
    ? greetingForHour(new Date().getHours())
    : { glyph: '👋', isNight: false };
  return (
    // `min-h-full`, not `h-full`: the starters (W8) made this block taller than
    // the viewport on a 320×640 screen, and a fixed-height centred box simply
    // overflowed — pushing the composer 39 px below the fold. With `min-h-full`
    // the block still centres when there is room, and grows into the parent's
    // scroll area when there is not, leaving the composer anchored.
    <div className="flex min-h-full flex-col items-center justify-center px-4 py-4 text-center">
      <div className="mb-6 flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-primary/20 backdrop-blur-sm animate-greet-float max-[380px]:mb-4 max-[380px]:h-16 max-[380px]:w-16">
        <AnimatedEmoji
          glyph={greeting.glyph}
          animate
          imgClassName="w-11 h-11"
          spanClassName="text-4xl"
        />
      </div>
      <div className="bg-card/60 backdrop-blur-md rounded-xl px-6 py-4 border border-border/20">
        <h2 className="text-xl font-semibold mb-2">{t('chat.empty_state.title')}</h2>
        <p className="text-sm text-muted-foreground max-w-md">
          {t('chat.empty_state.description')}
        </p>
        {greeting.isNight && (
          <p className="text-xs text-muted-foreground italic mt-3 max-w-md">
            {t('chat.empty_state.night_note')}
          </p>
        )}
      </div>
      {onStarterPick && (
        <EmptyConversationStarters
          onPick={onStarterPick}
          grounded={groundedSuggestions ?? []}
        />
      )}
    </div>
  );
}

/**
 * W8: three ways in, instead of a decorative dead end.
 *
 * The empty chat showed a greeting and nothing to act on — the one screen where
 * a newcomer has no idea what to type. Each starter PREFILLS the composer (the
 * follow-up chips' rail, never an auto-send) and is chosen to resolve on ANY
 * account, connected or not (see `lib/chat-starters`). The full catalogue stays
 * one link away in the FAQ, whose examples became clickable in W1.
 */
function EmptyConversationStarters({
  onPick,
  grounded,
}: {
  onPick: (text: string) => void;
  /** Suggestions the server could back with cached evidence (may be empty). */
  grounded: readonly ChatSuggestion[];
}) {
  const { t } = useTranslation();
  const rail = composeStarterRail(grounded, t);
  const anyGrounded = rail.some(entry => entry.grounded);

  return (
    <div className="mt-6 flex w-full max-w-md flex-col items-center gap-2 max-[380px]:mt-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {/* The heading tells the truth about what follows: "try for example"
            when the entries are generic, "from your day" once they name real
            things. Announcing invented context would be worse than none. */}
        {t(anyGrounded ? 'chat.suggestions.label' : 'chat.starters.label')}
      </p>
      <div
        role="group"
        aria-label={t(anyGrounded ? 'chat.suggestions.label' : 'chat.starters.label')}
        // Below `sm` each entry is a full-width 44 px row (one per line);
        // above it they fall back to the compact centred chips.
        className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:justify-center"
      >
        {rail.map(entry => (
          <button
            key={entry.key}
            type="button"
            onClick={() => onPick(entry.text)}
            title={entry.text}
            className={cn(
              'inline-flex max-w-full items-center rounded-full border text-xs font-medium',
              'transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              // 44 px touch target on mobile; compact chip from `sm` up.
              'min-h-11 w-full justify-start px-4 sm:min-h-0 sm:w-auto sm:justify-center sm:px-3 sm:py-1.5',
              entry.grounded
                ? 'border-primary/50 bg-primary/10 text-foreground hover:bg-primary/15'
                : 'border-primary/30 bg-primary/5 text-foreground/90 hover:border-primary/50 hover:bg-primary/10'
            )}
          >
            <span className="truncate">{entry.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * Top edge of the list: the scroll-up pagination sentinel (rendered while
 * older history remains; ``aria-hidden`` because it's an invisible trigger,
 * not content) and the polite loader row while a fetch is in flight.
 * Extracted from the render hotspot (CC discipline).
 */
function OlderHistoryEdge({
  hasMoreOlder,
  isLoadingOlder,
  sentinelRef,
}: {
  hasMoreOlder: boolean;
  isLoadingOlder: boolean;
  sentinelRef: React.RefObject<HTMLDivElement | null>;
}) {
  const { t } = useTranslation();
  return (
    <>
      {hasMoreOlder && <div ref={sentinelRef} aria-hidden="true" className="h-1" />}
      {isLoadingOlder && (
        <div
          role="status"
          aria-live="polite"
          className="flex justify-center py-3 text-xs text-muted-foreground"
        >
          <span className="animate-pulse">{t('chat.loading_older_messages')}</span>
        </div>
      )}
    </>
  );
}

/**
 * How long the freshly loaded history is kept pinned to the bottom.
 *
 * The list cannot be positioned on the commit that delivers it: the container
 * is `flex-1` inside a flex column, so on that first pass its height is not yet
 * constrained — `scrollHeight` equals `clientHeight` and there is nothing to
 * scroll. Content also keeps growing afterwards (React.lazy CodeBlock resolving
 * out of its Suspense fallback, images with no intrinsic size, web fonts).
 * A single jump therefore lands nowhere; the viewport is re-pinned every frame
 * until the layout settles, the reader takes over, or this window expires.
 */
const INITIAL_PIN_WINDOW_MS = 1500;

/** Stable empty list: keeps effect dependencies identical across renders. */
const NO_MESSAGES: Message[] = [];

export const ChatMessageList: React.FC<ChatMessageListProps> = ({
  messages,
  isTyping = false,
  activeStreamId = null,
  streamPhase = 'answer',
  browserScreenshot,
  hasMoreOlder = false,
  isLoadingOlder = false,
  onLoadOlder,
  groundedSuggestions,
  searchHighlight,
  onRetry,
  onPrefillComposer,
  onStarterPick,
  historyView = false,
  onReturnToPresent,
  ownSendTick = 0,
}) => {
  const { t } = useTranslation();

  // `messages` crosses an API/state boundary, and the defensive branch further
  // down renders an error card when it is not an array. That guard is a
  // *render* guard, though: the effects declared above it run on every render
  // regardless, so a null/undefined prop used to crash them (`messages[0]`)
  // before the card could ever be shown. Normalising once — against a stable
  // module-level constant, so the effect dependencies keep their identity —
  // makes the defensive branch actually reachable.
  const safeMessages = Array.isArray(messages) ? messages : NO_MESSAGES;

  // Client-only gate for the time-aware empty-chat greeting: the server SSRs
  // this 'use client' page in UTC while the browser hydrates in the user's
  // local timezone — computing the hour before mount would risk a hydration
  // mismatch. Render the neutral day glyph until mounted, then the real hour.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // Populate the Zustand store from server on mount (GET /psyche/state + /psyche/settings).
  // ChatMessage reads the store directly for fallback avatar data.
  usePsyche();

  const containerRef = useRef<HTMLDivElement>(null);
  const wasTypingRef = useRef(false);
  // Flag to cancel pending scroll-to-user if component unmounts during RAF
  const pendingScrollRef = useRef(false);
  // Scroll-up pagination state. ``prevFirstIdRef`` tracks the first-rendered
  // message id so we can detect a prepend; ``prevScrollHeightRef`` is captured
  // right before triggering ``onLoadOlder`` so the post-prepend useLayoutEffect
  // can offset ``scrollTop`` by the new content height — without this the
  // viewport jumps to the top as older messages push the existing ones down.
  //
  // ``wasPrependRef`` is the signal shared with the auto-scroll effect below:
  // when a prepend has just been applied, that effect MUST NOT run its
  // ``scrollIntoView`` (which would yank the viewport back to the bottom and
  // make the freshly loaded older messages invisible). The flag is raised
  // from the scroll-preservation useLayoutEffect once a prepend is detected,
  // and consumed (lowered) by the auto-scroll useEffect in the same render
  // cycle.
  const topSentinelRef = useRef<HTMLDivElement>(null);
  const prevFirstIdRef = useRef<string | null>(null);
  const prevScrollHeightRef = useRef<number | null>(null);
  const wasPrependRef = useRef(false);

  // UXR Lot 3 (A3) — reading invariant + floating button state.
  // ``prevOwnSendTickRef`` consumes the page's explicit own-send signal;
  // ``prevLastMessageIdRef`` detects new arrivals for the badge;
  // ``countedResponseIdRef`` dedupes the badge (a response is counted ONCE,
  // at its off-screen arrival OR its off-screen completion, never both);
  // ``settledRef`` arms the scroll listener only after the initial pin so the
  // load positioning can never flash the button.
  const prevOwnSendTickRef = useRef(ownSendTick);
  const prevLastMessageIdRef = useRef<string | null>(null);
  const prevContentHeightRef = useRef<number | null>(null);
  const countedResponseIdRef = useRef<string | null>(null);
  const settledRef = useRef(false);
  const [scrollUi, dispatchScrollUi] = useReducer(scrollUiReducer, SCROLL_UI_INITIAL);

  // Initial positioning. A freshly loaded conversation must open AT THE BOTTOM.
  //
  // Measured in a hermetic browser run, not reasoned about: on the commit that
  // delivers the history, the container reports `scrollHeight === clientHeight`
  // — it is `flex-1` inside a flex column and its height is not yet
  // constrained, so there is nothing to scroll and a jump there is a no-op.
  // The list then sits at scrollTop 0 with the pagination sentinel on screen,
  // the observer fires, the prepend raises ``wasPrependRef``, and that flag
  // SUPPRESSES the corrective scroll — leaving the reader on the very first
  // message while pagination loops (60 -> 780 messages in three seconds, with
  // zero ``scrollIntoView`` calls recorded).
  //
  // Both halves matter and both were verified by removing them one at a time
  // against the browser test: targeting the real scroller (a single jump on the
  // inner div does nothing at all), and re-pinning every frame until the layout
  // settles (a single correct jump is undone by the lazy content that lands
  // after it).
  //
  // The container carries the ``scroll-smooth`` class, which animates *every*
  // programmatic scroll — including a plain ``scrollTop`` assignment. The class
  // is therefore neutralised with an inline ``scroll-behavior: auto`` for the
  // duration of each pin, then restored. Deliberately not
  // ``scrollIntoView({ behavior: 'instant' })``: ``behavior`` is a WebIDL enum,
  // so a browser whose ``ScrollBehavior`` lacks ``instant`` throws a TypeError
  // — inside a layout effect, that takes the whole conversation down. WebKit is
  // in the E2E matrix and its support for that value is not settled, so this
  // uses only long-established APIs.
  //
  // Running it in a *layout* effect is what makes an extra pagination guard
  // unnecessary: all layout effects of a commit run before any passive effect,
  // so the viewport is already at the bottom by the time the
  // IntersectionObserver below is armed and takes its first reading.
  // True while the pin loop OWNS the viewport (its whole window, until the
  // reader takes over) — the auto-scroll effect skips messages updates during
  // that window. This is deliberately NOT a consumable one-shot flag: the
  // loop re-pins every frame, so a one-shot re-raised after its consumption
  // went stale and swallowed the FIRST post-load update — an own send never
  // scrolled (caught by the hermetic e2e, chat-scroll-follow.spec.ts).
  const pinActiveRef = useRef(false);
  const listIsEmpty = safeMessages.length === 0;

  useLayoutEffect(() => {
    if (listIsEmpty) return;
    const container = containerRef.current;
    if (!container) return;
    // The scroller may be an ancestor (see getScrollParent). Resolved lazily
    // inside the loop too, because on the first frames nothing overflows yet.

    let cancelled = false;
    const deadline = performance.now() + INITIAL_PIN_WINDOW_MS;
    pinActiveRef.current = true;

    // Instant jump — the `scroll-smooth` class animates even a scrollTop set;
    // the neutralization lives in the shared ``pinToBottom`` (lib/chat-scroll).
    const step = () => {
      if (cancelled) return;
      const own = containerRef.current;
      const el = own ? (getScrollParent(own) ?? own) : null;
      if (el) {
        if (el.scrollHeight > el.clientHeight) {
          pinToBottom(el);
          settledRef.current = true;
        }
      }
      if (performance.now() < deadline) {
        requestAnimationFrame(step);
      } else {
        pinActiveRef.current = false;
        // Arm the scroll listener even when nothing overflowed during the
        // window: a short first exchange followed by a long answer minutes
        // later must still get the floating button/badge (review finding —
        // settled means "initial positioning is over", not "overflowed").
        settledRef.current = true;
      }
    };

    /** Stop pinning. Teardown only — NOT a statement about the reader. */
    const stopPinning = () => {
      cancelled = true;
      pinActiveRef.current = false;
    };

    /** A real gesture: the reader took over — stop pinning and arm the
     *  scroll listener at once (the gesture IS the end of initial
     *  positioning, whatever the window timer says). */
    const onUserGesture = () => {
      stopPinning();
      settledRef.current = true;
    };

    requestAnimationFrame(step);
    container.addEventListener('wheel', onUserGesture, { passive: true, once: true });
    container.addEventListener('touchstart', onUserGesture, { passive: true, once: true });
    container.addEventListener('keydown', onUserGesture, { once: true });

    return () => {
      stopPinning();
      container.removeEventListener('wheel', onUserGesture);
      container.removeEventListener('touchstart', onUserGesture);
      container.removeEventListener('keydown', onUserGesture);
    };
    // Deliberately NOT keyed on `safeMessages`: the pin window must survive the
    // message updates that happen during it, and re-running would tear down the
    // loop on every append.
  }, [listIsEmpty]);

  // Auto-scroll behavior (UXR Lot 3 — the reading invariant):
  // - An OWN send (new user message) always jumps to the bottom.
  // - Otherwise the reader's LIVE position rules: at bottom → follow the
  //   stream / align on stream end (today's behavior); away → STAY — a
  //   streaming answer, a proactive arrival or a stream completion must never
  //   yank someone re-reading the thread. Off-screen responses feed the
  //   floating button's badge instead (once per response id).
  // - Skipped entirely when the last messages update was a scroll-up prepend
  //   (the scroll-preservation useLayoutEffect has already restored
  //   ``scrollTop``) or the initial positioning (layout effect above).
  // Geometry is measured AT DECISION TIME — content grows without scroll
  // events (lazy code blocks, images), so a cached flag would go stale.
  useEffect(() => {
    const lastMessage = safeMessages[safeMessages.length - 1];
    const lastId = lastIdOf(safeMessages);
    const isNewLast = lastId !== prevLastMessageIdRef.current;
    const isNewOwnMessage = ownSendTick !== prevOwnSendTickRef.current;
    const scroller = resolveScrollerOf(containerRef.current);
    const finishTurn = () => {
      prevLastMessageIdRef.current = lastId;
      prevOwnSendTickRef.current = ownSendTick;
      prevContentHeightRef.current = scroller ? scroller.scrollHeight : null;
      wasTypingRef.current = isTyping;
    };

    if (pinActiveRef.current) {
      // The initial-positioning loop owns the viewport (it re-pins every
      // frame until the layout settles or the reader takes over) — fighting
      // it here would animate scrolls that already happened.
      finishTurn();
      return;
    }
    if (wasPrependRef.current) {
      // Consume the prepend flag and short-circuit. Still update the refs so
      // the streaming-just-ended branch fires correctly next time.
      wasPrependRef.current = false;
      finishTurn();
      return;
    }

    const decision = decideFollow({
      atBottom: isScrollerAtBottom(scroller, prevContentHeightRef.current),
      isNewOwnMessage,
    });
    const badgeResponse = () => {
      if (lastMessage?.role === 'assistant' && lastId !== countedResponseIdRef.current) {
        countedResponseIdRef.current = lastId;
        dispatchScrollUi({ type: 'new-assistant-message' });
      }
    };

    if (!isTyping && wasTypingRef.current) {
      if (decision === 'stay') {
        // A response finished off-screen — badge it (deduped by id).
        badgeResponse();
      } else {
        // Streaming just ended at the bottom: scroll to the last user message
        // aligned at top. Double RAF ensures the DOM is fully painted.
        pendingScrollRef.current = true;

        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            // Check if scroll was cancelled (component unmounted or new effect triggered)
            if (!pendingScrollRef.current || !containerRef.current) return;

            // Find all user message wrappers and get the last one
            const userMessageWrappers = containerRef.current.querySelectorAll<HTMLElement>(
              '[data-message-role="user"]'
            );

            if (userMessageWrappers.length > 0) {
              const lastUserMessage = userMessageWrappers[userMessageWrappers.length - 1];
              // scroll-mt-24 (96px) clears the sticky frosted header that now
              // overlays the scrollport's top (2026-07-30) + breathing room
              lastUserMessage.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }

            pendingScrollRef.current = false;
          });
        });
      }
    } else if (decision === 'follow') {
      // INSTANT per-batch pin — a smooth follow measures its own running
      // animation as "away" on the next token batch and strands the viewport
      // mid-thread (e2e-caught); instant pinning is the classic chat
      // behavior. On an own send the jump IS the badge reset.
      if (scroller) pinToBottom(scroller);
      if (isNewOwnMessage) dispatchScrollUi({ type: 'jumped-to-bottom' });
    } else if (isNewLast) {
      // New assistant/proactive message landed while the reader is away.
      badgeResponse();
    }

    finishTurn();

    // Cleanup: cancel pending scroll if effect re-runs or component unmounts
    return () => {
      pendingScrollRef.current = false;
    };
  }, [safeMessages, isTyping, ownSendTick]);

  // Floating-button visibility (UXR Lot 3): scroll listener captured at the
  // window (scroll does not bubble, but it CAN be captured), so the real
  // scroller is resolved lazily — at mount nothing overflows yet and the
  // page's own wrapper only becomes scrollable later. rAF-throttled, armed
  // only once the initial pin has settled.
  useEffect(() => {
    if (listIsEmpty) return;
    let rafId: number | null = null;
    const onScroll = () => {
      if (!settledRef.current || rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        const scroller = resolveScrollerOf(containerRef.current);
        if (scroller) {
          dispatchScrollUi({ type: 'distance', distance: distanceToBottom(scroller) });
        }
      });
    };
    window.addEventListener('scroll', onScroll, { capture: true, passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll, { capture: true });
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [listIsEmpty]);

  // Floating-button click: in history view, delegate the page swap to the
  // parent (QW-2 semantics); otherwise instant jump + badge reset.
  const handleScrollButtonClick = useCallback(() => {
    if (historyView) {
      onReturnToPresent?.();
      return;
    }
    const scroller = resolveScrollerOf(containerRef.current);
    if (scroller) pinToBottom(scroller);
    dispatchScrollUi({ type: 'jumped-to-bottom' });
  }, [historyView, onReturnToPresent]);

  // Scroll-position preservation after a scroll-up prepend.
  //
  // Runs synchronously after the DOM mutation (useLayoutEffect) so the
  // viewport never visibly jumps. Detection is based on the first message id
  // changing while ``prevScrollHeightRef`` is set — that combo only occurs
  // when the parent prepended older messages in response to ``onLoadOlder``.
  // When a prepend is detected, ``wasPrependRef`` is raised so the auto-scroll
  // useEffect below knows to skip its scrollIntoView this cycle.
  useLayoutEffect(() => {
    const own = containerRef.current;
    const container = own ? (getScrollParent(own) ?? own) : null;
    const newFirstId = safeMessages[0]?.id ?? null;

    if (
      container &&
      prevScrollHeightRef.current !== null &&
      prevFirstIdRef.current !== null &&
      newFirstId !== null &&
      newFirstId !== prevFirstIdRef.current
    ) {
      const delta = container.scrollHeight - prevScrollHeightRef.current;
      if (delta > 0) {
        container.scrollTop += delta;
      }
      wasPrependRef.current = true;
    }

    prevFirstIdRef.current = newFirstId;
    prevScrollHeightRef.current = null;
  }, [safeMessages]);

  // IntersectionObserver on the top sentinel — fires ``onLoadOlder`` as soon
  // as the user scrolls within ``rootMargin`` of the top of the list. Re-bound
  // whenever pagination availability or the loading flag changes so we don't
  // call back into the parent while a fetch is already in flight.
  useEffect(() => {
    if (!onLoadOlder || !hasMoreOlder) return;
    // Never paginate before the viewport has been placed at the bottom. At
    // mount the list sits at scrollTop 0, so the sentinel is on screen: an
    // observer armed here fires immediately, prepends history nobody asked
    // for, and the prepend raises ``wasPrependRef`` — which SUPPRESSES the
    // scroll-to-bottom. The list then stays at 0, the sentinel stays visible,
    // and it loops: a hermetic browser run loaded 60 -> 780 messages in three
    // seconds while the reader sat on the very first message.
    const sentinel = topSentinelRef.current;
    const own = containerRef.current;
    if (!sentinel || !own) return;
    // Rooting the observer on a box that never scrolls makes the sentinel
    // permanently visible — the runaway pagination this guard cannot fix alone.
    const container = getScrollParent(own) ?? own;

    const observer = new IntersectionObserver(
      entries => {
        const entry = entries[0];
        if (!entry?.isIntersecting || isLoadingOlder) return;
        // "The sentinel is visible" is not the same as "the reader asked for
        // older history". While a conversation loads, the list sits at
        // scrollTop 0 with the sentinel on screen, so this fires unprompted —
        // and because each prepend raises ``wasPrependRef``, which suppresses
        // the corrective scroll, the list never leaves the top and the
        // observer fires again. Measured in a hermetic browser run: 60 -> 780
        // messages in three seconds, the reader pinned to the first message.
        //
        // Requiring a real scroll gesture makes the trigger deterministic
        // instead of dependent on layout timing. The exception is a list that
        // does not overflow: there is nothing to scroll, so auto-filling the
        // viewport is the only way more history can ever arrive.
        // Capture pre-prepend height — useLayoutEffect above uses it to
        // restore the scroll position after the new rows mount.
        prevScrollHeightRef.current = container.scrollHeight;
        onLoadOlder();
      },
      { root: container, rootMargin: '200px 0px 0px 0px' }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [onLoadOlder, hasMoreOlder, isLoadingOlder]);

  // DEFENSIVE: Handle case where messages is not an array
  if (!Array.isArray(messages)) {
    // Log error without exposing message content (PII protection)
    logger.error('messages_invalid_type', undefined, {
      component: 'ChatMessageList',
      receivedType: typeof messages,
      isNull: messages === null,
      isUndefined: messages === undefined,
    });
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-4">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-destructive/20 backdrop-blur-sm">
          <MessageSquare className="h-10 w-10 text-destructive" />
        </div>
        <div className="bg-card/60 backdrop-blur-md rounded-xl px-6 py-4 border border-destructive/20">
          <h2 className="text-xl font-semibold mb-2 text-destructive">{t('chat.error.title')}</h2>
          <p className="text-sm text-muted-foreground max-w-md">{t('chat.error.message')}</p>
        </div>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <EmptyConversation
        mounted={mounted}
        onStarterPick={onStarterPick}
        groundedSuggestions={groundedSuggestions}
      />
    );
  }

  const lastAssistantId = getLastAssistantMessageId(messages);
  const lastErrorId = lastRetryableErrorId(messages);

  return (
    // pt-8 (32px) provides top padding; scroll-mt-8 on messages must match for proper scroll alignment
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-2 pt-8 pb-6 mobile:px-6 scroll-smooth"
    >
      <div className="mobile:max-w-5xl mobile:mx-auto [&>*:first-child]:mt-2">
        <OlderHistoryEdge
          hasMoreOlder={hasMoreOlder}
          isLoadingOlder={isLoadingOlder}
          sentinelRef={topSentinelRef}
        />
        {messages.map(message => (
          // scroll-mt-24 clears the sticky frosted header overlaying the
          // scrollport's top (2026-07-30): block:'start' targets would
          // otherwise land hidden under the glass.
          <div
            key={message.id}
            data-message-role={message.role}
            data-message-id={message.id}
            className="scroll-mt-24"
          >
            <ChatMessage
              message={message}
              isUser={message.role === 'user'}
              isLatestAssistant={message.id === lastAssistantId}
              isActiveStream={message.id === activeStreamId}
              streamPhase={streamPhase}
              searchHighlight={searchHighlight}
              onRetry={message.id === lastErrorId ? onRetry : undefined}
              onPrefillComposer={onPrefillComposer}
            />
          </div>
        ))}

        {/* Browser progressive screenshot — inline in chat flow */}
        {browserScreenshot && <BrowserScreenshotOverlay screenshot={browserScreenshot} />}

        {/* Typing indicator */}
        {isTyping && (
          <div className="flex gap-3 mb-4 flex-row-reverse">
            <div className="bg-card/60 backdrop-blur-md px-4 py-3 rounded-lg rounded-tr-none border border-border/20">
              <TypingIndicator />
            </div>
          </div>
        )}

        {/* Floating return affordance + off-screen announcement (UXR Lot 3). */}
        <ScrollUiOverlay
          historyView={historyView}
          scrollUi={scrollUi}
          onClick={handleScrollButtonClick}
        />
      </div>
    </div>
  );
};

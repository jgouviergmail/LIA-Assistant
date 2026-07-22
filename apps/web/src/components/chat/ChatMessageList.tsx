import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Message, BrowserScreenshotData } from '@/types/chat';
import type { StreamPhase } from '@/types/chat-state';
import { ChatMessage } from './ChatMessage';
import { BrowserScreenshotOverlay } from './BrowserScreenshotOverlay';
import { TypingIndicator } from './TypingIndicator';
import { AnimatedEmoji } from '@/components/ui/animated-emoji';
import { MessageSquare } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { usePsyche } from '@/hooks/usePsyche';
import { logger } from '@/lib/logger';

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
  searchHighlight,
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

  const messagesEndRef = useRef<HTMLDivElement>(null);
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
  // Raised by the first successful pin, consumed by the auto-scroll effect so
  // it does not replay as an animation a scroll that already happened.
  const justPositionedRef = useRef(false);
  const listIsEmpty = safeMessages.length === 0;

  useLayoutEffect(() => {
    if (listIsEmpty) return;
    const container = containerRef.current;
    if (!container) return;
    // The scroller may be an ancestor (see getScrollParent). Resolved lazily
    // inside the loop too, because on the first frames nothing overflows yet.

    let cancelled = false;
    const deadline = performance.now() + INITIAL_PIN_WINDOW_MS;

    /** Instant jump — the `scroll-smooth` class animates even a scrollTop set. */
    const pinToBottom = (el: HTMLElement) => {
      const style = el.style;
      const previous = style.getPropertyValue('scroll-behavior');
      style.setProperty('scroll-behavior', 'auto');
      el.scrollTop = el.scrollHeight;
      if (previous) style.setProperty('scroll-behavior', previous);
      else style.removeProperty('scroll-behavior');
    };

    const step = () => {
      if (cancelled) return;
      const own = containerRef.current;
      const el = own ? (getScrollParent(own) ?? own) : null;
      if (el) {
        if (el.scrollHeight > el.clientHeight) {
          pinToBottom(el);
          justPositionedRef.current = true;
        }
      }
      if (performance.now() < deadline) requestAnimationFrame(step);
    };

    /** Stop pinning. Teardown only — NOT a statement about the reader. */
    const stopPinning = () => {
      cancelled = true;
    };

    /** A real gesture: the reader took over, stop pinning at once. */
    const onUserGesture = () => {
      stopPinning();
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

  // Auto-scroll behavior:
  // - Default: scroll to bottom (preserves original behavior for history load, new messages, etc.)
  // - When streaming ends: scroll to last user message aligned at top
  // - Skipped entirely when the last messages update was a scroll-up prepend
  //   (the scroll-preservation useLayoutEffect has already restored ``scrollTop``;
  //   scrolling to bottom here would undo it and hide the freshly loaded
  //   older messages).
  useEffect(() => {
    if (justPositionedRef.current) {
      // The layout effect above already placed the viewport at the bottom,
      // synchronously and before paint. Replaying it here would animate a
      // scroll that has already happened.
      justPositionedRef.current = false;
      wasTypingRef.current = isTyping;
      return;
    }
    if (wasPrependRef.current) {
      // Consume the prepend flag and short-circuit. Still update
      // ``wasTypingRef`` so the streaming-just-ended branch fires correctly
      // on the next non-prepend update.
      wasPrependRef.current = false;
      wasTypingRef.current = isTyping;
      return;
    }
    if (!isTyping && wasTypingRef.current) {
      // Streaming just ended: scroll to last user message aligned at top
      // Double RAF ensures the DOM is fully painted before scrolling
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
            // scroll-mt-8 (32px) matches container's pt-8 for visual alignment
            lastUserMessage.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }

          pendingScrollRef.current = false;
        });
      });
    } else {
      // All other cases: scroll to bottom (streaming follow, history load, etc.)
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }

    // Update previous state AFTER the condition check
    wasTypingRef.current = isTyping;

    // Cleanup: cancel pending scroll if effect re-runs or component unmounts
    return () => {
      pendingScrollRef.current = false;
    };
  }, [safeMessages, isTyping]);

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
    // Time-aware greeting (☕ morning · 👋 day · 🌛 evening · 😴 deep night) —
    // AnimatedEmoji falls back to the static glyph on missing asset / reduced
    // motion. Neutral day glyph until mounted (avoids the SSR hydration mismatch).
    const greeting: TimeGreeting = mounted
      ? greetingForHour(new Date().getHours())
      : { glyph: '👋', isNight: false };
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-4">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-primary/20 backdrop-blur-sm animate-greet-float">
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
      </div>
    );
  }

  const lastAssistantId = getLastAssistantMessageId(messages);

  return (
    // pt-8 (32px) provides top padding; scroll-mt-8 on messages must match for proper scroll alignment
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-2 pt-8 pb-6 mobile:px-6 scroll-smooth"
    >
      <div className="mobile:max-w-5xl mobile:mx-auto [&>*:first-child]:mt-2">
        {/* Scroll-up sentinel: rendered while older history remains. The
            IntersectionObserver above fires ``onLoadOlder`` as soon as it
            enters the viewport. ``aria-hidden`` because it's an invisible
            scroll trigger, not content. */}
        {hasMoreOlder && <div ref={topSentinelRef} aria-hidden="true" className="h-1" />}
        {isLoadingOlder && (
          <div
            role="status"
            aria-live="polite"
            className="flex justify-center py-3 text-xs text-muted-foreground"
          >
            <span className="animate-pulse">{t('chat.loading_older_messages')}</span>
          </div>
        )}
        {messages.map(message => (
          // scroll-mt-8 must match container's pt-8 for scrollIntoView alignment
          <div
            key={message.id}
            data-message-role={message.role}
            data-message-id={message.id}
            className="scroll-mt-8"
          >
            <ChatMessage
              message={message}
              isUser={message.role === 'user'}
              isLatestAssistant={message.id === lastAssistantId}
              isActiveStream={message.id === activeStreamId}
              streamPhase={streamPhase}
              searchHighlight={searchHighlight}
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

        {/* Element for auto-scroll */}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
};

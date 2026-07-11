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

export const ChatMessageList: React.FC<ChatMessageListProps> = ({
  messages,
  isTyping = false,
  activeStreamId = null,
  streamPhase = 'answer',
  browserScreenshot,
  hasMoreOlder = false,
  isLoadingOlder = false,
  onLoadOlder,
}) => {
  const { t } = useTranslation();

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

  // Auto-scroll behavior:
  // - Default: scroll to bottom (preserves original behavior for history load, new messages, etc.)
  // - When streaming ends: scroll to last user message aligned at top
  // - Skipped entirely when the last messages update was a scroll-up prepend
  //   (the scroll-preservation useLayoutEffect has already restored ``scrollTop``;
  //   scrolling to bottom here would undo it and hide the freshly loaded
  //   older messages).
  useEffect(() => {
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
  }, [messages, isTyping]);

  // Scroll-position preservation after a scroll-up prepend.
  //
  // Runs synchronously after the DOM mutation (useLayoutEffect) so the
  // viewport never visibly jumps. Detection is based on the first message id
  // changing while ``prevScrollHeightRef`` is set — that combo only occurs
  // when the parent prepended older messages in response to ``onLoadOlder``.
  // When a prepend is detected, ``wasPrependRef`` is raised so the auto-scroll
  // useEffect below knows to skip its scrollIntoView this cycle.
  useLayoutEffect(() => {
    const container = containerRef.current;
    const newFirstId = messages[0]?.id ?? null;

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
  }, [messages]);

  // IntersectionObserver on the top sentinel — fires ``onLoadOlder`` as soon
  // as the user scrolls within ``rootMargin`` of the top of the list. Re-bound
  // whenever pagination availability or the loading flag changes so we don't
  // call back into the parent while a fetch is already in flight.
  useEffect(() => {
    if (!onLoadOlder || !hasMoreOlder) return;
    const sentinel = topSentinelRef.current;
    const container = containerRef.current;
    if (!sentinel || !container) return;

    const observer = new IntersectionObserver(
      entries => {
        const entry = entries[0];
        if (entry?.isIntersecting && !isLoadingOlder) {
          // Capture pre-prepend height — useLayoutEffect above uses it to
          // restore the scroll position after the new rows mount.
          prevScrollHeightRef.current = container.scrollHeight;
          onLoadOlder();
        }
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
            <p className="text-xs text-muted-foreground/70 italic mt-3 max-w-md">
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

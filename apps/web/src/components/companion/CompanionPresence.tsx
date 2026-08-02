/**
 * CompanionPresence — a floating mini-avatar of LIA that follows across the
 * dashboard pages (home, settings, faq), reflecting a real system state:
 *
 *  - rest    : default — the current psyche mood emoji, gently floating.
 *  - working : a background run is in progress (ADR-117 GET /agents/runs/active).
 *  - notification (overlay badge) : unread proactive / reminder / subagent /
 *              scheduled-action notifications, with a one-shot attention wobble.
 *
 * Hidden on the chat page (the real AssistantAvatar already lives there); while
 * hidden it also disables its SSE + polling, so exactly one notifications
 * connection is ever active. Dismissable (session-scoped) so it never
 * permanently hides a signal. Reuses AssistantAvatar / TypingIndicator and the
 * existing float/bell-ring keyframes (all in the reduced-motion kill-switch).
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';

import { cn } from '@/lib/utils';
import { AssistantAvatar } from '@/components/psyche/AssistantAvatar';
import { TypingIndicator } from '@/components/chat/TypingIndicator';
import { usePsycheStore } from '@/stores/psycheStore';
import { useNotifications, type NotificationType } from '@/hooks/useNotifications';
import { fetchActiveRun } from '@/lib/api/chat';
import { getLanguageFromPath, buildLocalizedPath } from '@/utils/i18n-path-utils';
import { fallbackLng } from '@/i18n/settings';
import type { PsycheStateSummary } from '@/types/psyche';

/** Notification types that count toward the companion's unread badge. */
const COUNTED_TYPES: ReadonlySet<NotificationType> = new Set<NotificationType>([
  'proactive_interest',
  'proactive_heartbeat',
  'reminder',
  'subagent_result',
  'scheduled_action',
]);

const ACTIVE_RUN_POLL_MS = 6000;
const BELL_RING_MS = 650;

/** True when the path is the chat page (any locale) — the companion hides there. */
export function isChatRoute(pathname: string | null): boolean {
  return !!pathname && pathname.includes('/dashboard/chat');
}

/**
 * Localized href to the chat page, resolved the same way the dashboard layout
 * builds its nav links — robust whether or not the locale prefixes the (clean)
 * URL. Guards against naive `pathname.split('/')[1]` locale extraction.
 */
export function companionChatHref(pathname: string | null): string {
  const lng = (pathname ? getLanguageFromPath(pathname) : fallbackLng) || fallbackLng;
  return buildLocalizedPath('/dashboard/chat', lng);
}

export interface CompanionState {
  base: 'rest' | 'working';
  showBadge: boolean;
  badgeCount: number;
}

/** Display contract from the two live signals. Badge overlays either base state. */
export function deriveCompanionState(input: {
  working: boolean;
  unreadCount: number;
}): CompanionState {
  return {
    base: input.working ? 'working' : 'rest',
    showBadge: input.unreadCount > 0,
    badgeCount: input.unreadCount,
  };
}

interface CompanionPresenceProps {
  /** Only render/subscribe when the user is authenticated. */
  isAuthenticated: boolean;
}

export function CompanionPresence({ isAuthenticated }: CompanionPresenceProps) {
  const { t } = useTranslation();
  const router = useRouter();
  const pathname = usePathname();
  const onChat = isChatRoute(pathname);

  // Client-only gate: the dashboard layout is a 'use client' page that is still
  // SSR'd once; defer rendering until mount to avoid any hydration mismatch.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [dismissed, setDismissed] = useState(false);
  const [working, setWorking] = useState(false);
  const [unread, setUnread] = useState(0);
  const [ringing, setRinging] = useState(false);
  const ringTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const active = isAuthenticated && !onChat && !dismissed;

  // Stable callback — an inline one would change identity every render and make
  // useNotifications tear down + rebuild its EventSource on each render (a
  // reconnect storm). Uses only stable setters/refs, so [] deps are safe.
  const handleNotification = useCallback((n: { type: NotificationType }) => {
    if (!COUNTED_TYPES.has(n.type)) return;
    setUnread(c => c + 1);
    setRinging(true);
    if (ringTimeout.current) clearTimeout(ringTimeout.current);
    ringTimeout.current = setTimeout(() => setRinging(false), BELL_RING_MS);
  }, []);

  // Notification badge: reuse the battle-tested SSE hook (no FCM double-handling).
  // Disabled on the chat page so its own useNotifications stays the only one.
  useNotifications({
    isAuthenticated: active,
    enableSSE: active,
    enableFCM: false,
    onNotification: handleNotification,
  });
  useEffect(() => {
    return () => {
      if (ringTimeout.current) clearTimeout(ringTimeout.current);
    };
  }, []);

  // Clear the badge as soon as the user is on chat (by any means — nav bar or
  // the companion): they are now where the notifications actually live.
  useEffect(() => {
    if (onChat) setUnread(0);
  }, [onChat]);

  // Working state: poll the ADR-117 active-run endpoint at a gentle cadence,
  // only while the companion is live (off-chat), so no duplication with chat.
  useEffect(() => {
    if (!active) {
      setWorking(false);
      return;
    }
    let cancelled = false;
    const check = async () => {
      try {
        const status = await fetchActiveRun();
        if (!cancelled) setWorking(Boolean(status.active));
      } catch {
        /* transient — keep the previous value */
      }
    };
    check();
    const id = setInterval(check, ACTIVE_RUN_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [active]);

  const psyche = usePsycheStore();
  const psycheState: PsycheStateSummary | null =
    psyche.enabled && psyche.displayAvatar
      ? {
          mood_label: psyche.moodLabel,
          mood_color: psyche.moodColor,
          mood_pleasure: psyche.moodPleasure,
          mood_arousal: psyche.moodArousal,
          mood_dominance: psyche.moodDominance,
          active_emotion: psyche.activeEmotion,
          emotion_intensity: psyche.emotionIntensity,
          relationship_stage: psyche.relationshipStage,
        }
      : null;

  if (!mounted || !isAuthenticated || onChat) return null;

  const state = deriveCompanionState({ working, unreadCount: unread });

  // Dismissed → a tiny restore dot in the corner (never fully gone).
  if (dismissed) {
    return (
      <button
        type="button"
        onClick={() => setDismissed(false)}
        aria-label={t('companion.restore')}
        // The dot stays 12 px; the TARGET is 44. The box is anchored to the
        // same corner and grows inward, so the dot does not move a pixel.
        className="group fixed bottom-6 right-6 z-40 flex h-11 w-11 items-end justify-end"
      >
        <span className="h-3 w-3 rounded-full bg-primary/60 shadow-md ring-2 ring-background transition-colors group-hover:bg-primary" />
      </button>
    );
  }

  const openChat = () => {
    setUnread(0);
    router.push(companionChatHref(pathname));
  };

  const stateLabel = state.showBadge
    ? t('companion.aria_state', { count: state.badgeCount })
    : t('companion.open_chat');

  return (
    <div className="fixed bottom-6 right-6 z-40 flex flex-col items-center gap-1">
      {/* Working: a small "thinking" bubble above the avatar */}
      {state.base === 'working' && (
        <div className="rounded-full bg-card/80 backdrop-blur-md border border-border/30 px-2.5 py-1.5 shadow-md motion-safe:animate-greet-float">
          <TypingIndicator />
        </div>
      )}

      <div className="group relative">
        <button
          type="button"
          onClick={openChat}
          aria-label={stateLabel}
          // The avatar is 40 px; the TARGET must be 44. The ring/shadow move
          // onto an inner span so the button can grow to a touch-sized box
          // without the companion itself looking bigger.
          className={cn(
            'flex h-11 w-11 items-center justify-center rounded-full transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-primary',
            state.base === 'rest' && 'motion-safe:animate-greet-float'
          )}
        >
          <span className="block rounded-full shadow-lg ring-2 ring-background">
            <AssistantAvatar
              psycheState={psycheState}
              animateEmoji
              animate={state.base === 'working'}
              ring={ringing}
            />
          </span>
        </button>

        {/* Notification count badge */}
        {state.showBadge && (
          <span
            aria-hidden="true"
            // -0.5 rather than -1: the button box grew from 40 to 44 px for the
            // touch target, so the corner moved out by 2 px. Compensating here
            // keeps the badge exactly where it sat against the avatar.
            className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-destructive text-destructive-foreground text-[10px] font-bold tabular-nums shadow ring-2 ring-background"
          >
            {state.badgeCount > 9 ? '9+' : state.badgeCount}
          </span>
        )}

        {/* Minimize control — on hover, and permanently where hover does not
            exist. Two things were wrong at once on a phone: the dot was 16 px,
            and `opacity-0` with no hover made it INVISIBLE YET CLICKABLE — so
            minimizing was unreachable on purpose-built taps and reachable by
            accident. Enlarging the hit area without showing the control would
            have made that trap bigger, not smaller. */}
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label={t('companion.minimize')}
          // 44 px box growing AWAY from the avatar (up-left, where nothing is),
          // with the 16 px dot pinned to its bottom-right corner — the visual
          // stays put and the enlarged target never steals a tap meant for the
          // chat button underneath.
          className="absolute -top-[30px] -left-[30px] flex h-11 w-11 items-end justify-end opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"
        >
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-muted text-muted-foreground shadow ring-1 ring-border">
            <X className="h-2.5 w-2.5" />
          </span>
        </button>
      </div>
    </div>
  );
}

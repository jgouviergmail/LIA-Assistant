/**
 * Zustand store for the expressive-eyes live signals (ephemeral, not persisted).
 *
 * Non-React code records here what the eyes should notice:
 *  - SSE `execution_step` handler → kind of the latest step (reasoning/tool)
 *  - chat page notification callback → proactive-notification ping
 *  - chat input change callback → typing activity
 *  - chat page done-transition effect → held post-response reaction
 *
 * Timestamps are stored raw and interpreted through the pure TTL selectors
 * (`isNotificationLive`, `isTypingLive`, `liveReaction`) so tests inject exact
 * clocks — same doctrine as the injected RNG in the expression engine.
 */

import { create } from 'zustand';

import {
  NOTIFICATION_PING_MS,
  REACTION_HOLD_MS,
  TYPING_ACTIVE_MS,
  type EyeExpression,
} from '@/components/eyes/expression-engine';

/** Alias kept local so non-widget callers don't import the whole engine. */
export const NOTIFICATION_SIGNAL_TTL_MS = NOTIFICATION_PING_MS;

export type EyesStepKind = 'reasoning' | 'tool';

interface EyesSignalsState {
  /** Kind of the latest execution step of the current turn. */
  lastStepKind: EyesStepKind | null;
  /** Timestamp of the last proactive notification (ms epoch), or null. */
  notificationAt: number | null;
  /** Timestamp of the last keystroke in the chat input (ms epoch), or null. */
  typingAt: number | null;
  /** Held post-response reaction with its start timestamp, or null. */
  reaction: { expression: EyeExpression; at: number } | null;

  // Recorders (non-React callers)
  recordStep: (kind: EyesStepKind) => void;
  recordNotification: (at?: number) => void;
  recordTyping: (at?: number) => void;
  setReaction: (expression: EyeExpression | null, at?: number) => void;
  /** A new turn starts: per-turn signals must not leak into it. */
  beginTurn: () => void;
  reset: () => void;

  // Pure TTL selectors (clock injected)
  isNotificationLive: (now: number) => boolean;
  isTypingLive: (now: number) => boolean;
  liveReaction: (now: number) => EyeExpression | null;
}

const INITIAL = {
  lastStepKind: null as EyesStepKind | null,
  notificationAt: null as number | null,
  typingAt: null as number | null,
  reaction: null as { expression: EyeExpression; at: number } | null,
};

export const useEyesSignalsStore = create<EyesSignalsState>((set, get) => ({
  ...INITIAL,

  recordStep: kind => set({ lastStepKind: kind }),

  recordNotification: (at = Date.now()) => set({ notificationAt: at }),

  recordTyping: (at = Date.now()) => set({ typingAt: at }),

  setReaction: (expression, at = Date.now()) =>
    set({ reaction: expression ? { expression, at } : null }),

  beginTurn: () => set({ lastStepKind: null, reaction: null }),

  reset: () => set(INITIAL),

  isNotificationLive: now => {
    const at = get().notificationAt;
    return at !== null && now - at < NOTIFICATION_SIGNAL_TTL_MS;
  },

  isTypingLive: now => {
    const at = get().typingAt;
    return at !== null && now - at < TYPING_ACTIVE_MS;
  },

  liveReaction: now => {
    const reaction = get().reaction;
    if (!reaction || now - reaction.at >= REACTION_HOLD_MS) return null;
    return reaction.expression;
  },
}));

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

import type { ToneAccent, ToneAnnotation } from '@/components/eyes/tone';

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
  /** Held post-response reaction with its start timestamp, or null.
   * `emphasis` is how hard the face plays it (never how LIA feels — that
   * is the psyche's job, and it is not an animation input). */
  reaction: {
    expression: EyeExpression;
    emphasis: number;
    accent: ToneAccent;
    at: number;
  } | null;
  /** The register the answering model declared for the turn in flight.
   *
   * Parked here by the SSE `done` handler and read a moment later, when the
   * status transition resolves the reaction. The two are separate events on
   * purpose: `done` carries the annotation, the transition is what decides
   * a turn actually COMPLETED (a reload hydrating history must not react). */
  pendingTone: ToneAnnotation | null;

  // Recorders (non-React callers)
  recordStep: (kind: EyesStepKind) => void;
  recordNotification: (at?: number) => void;
  recordTyping: (at?: number) => void;
  setReaction: (
    expression: EyeExpression | null,
    emphasis?: number,
    accent?: ToneAccent,
    at?: number
  ) => void;
  /** Hold the tone the `done` event carried, for the transition to consume. */
  setTone: (tone: ToneAnnotation | null) => void;
  /** A new turn starts: per-turn signals must not leak into it. */
  beginTurn: () => void;
  reset: () => void;

  // Pure TTL selectors (clock injected)
  isNotificationLive: (now: number) => boolean;
  isTypingLive: (now: number) => boolean;
  liveReaction: (now: number) => EyeExpression | null;
  /** How forcefully the last answer was written, while its reaction is held;
   * 1 the rest of the time. */
  liveEmphasis: (now: number) => number;
  /** The one-shot beat the answer earned, while its reaction is held. */
  liveAccent: (now: number) => ToneAccent;
}

const INITIAL = {
  lastStepKind: null as EyesStepKind | null,
  notificationAt: null as number | null,
  typingAt: null as number | null,
  reaction: null as {
    expression: EyeExpression;
    emphasis: number;
    accent: ToneAccent;
    at: number;
  } | null,
  pendingTone: null as ToneAnnotation | null,
};

export const useEyesSignalsStore = create<EyesSignalsState>((set, get) => ({
  ...INITIAL,

  recordStep: kind => set({ lastStepKind: kind }),

  recordNotification: (at = Date.now()) => set({ notificationAt: at }),

  recordTyping: (at = Date.now()) => set({ typingAt: at }),

  setReaction: (expression, emphasis = 1, accent = 'none', at = Date.now()) =>
    set({ reaction: expression ? { expression, emphasis, accent, at } : null }),

  setTone: tone => set({ pendingTone: tone }),

  beginTurn: () => set({ lastStepKind: null, reaction: null, pendingTone: null }),

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

  liveEmphasis: now => {
    const reaction = get().reaction;
    if (!reaction || now - reaction.at >= REACTION_HOLD_MS) return 1;
    return reaction.emphasis;
  },

  liveAccent: now => {
    const reaction = get().reaction;
    if (!reaction || now - reaction.at >= REACTION_HOLD_MS) return 'none';
    return reaction.accent;
  },
}));

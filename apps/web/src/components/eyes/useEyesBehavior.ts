'use client';

/**
 * useEyesBehavior — the living part of the expressive eyes.
 *
 * Wires the pure expression engine to the live world:
 *  - re-derives the frame on prop changes, store updates (signals / psyche /
 *    voice) and a 1 Hz heartbeat (paused while the tab is hidden) that ages
 *    the TTL signals, the inactivity stage and the error hold
 *  - schedules spontaneous blinks (3-7 s cadence, occasional double blink),
 *    skipped while hidden, asleep or under reduced motion
 *  - tracks user activity (pointer/keys/wheel/touch + message sends) for the
 *    progressive dozing-off stages
 *  - offers a one-shot `wink()` for the double-click easter egg
 *
 * All timers are owned and cleared here; nothing waits on `animationend`
 * (jsdom never fires it) — the blink flag is dropped on its own timeout.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  BLINK_DURATION_MS,
  DOUBLE_BLINK_GAP_MS,
  EMOTE_EXIT_MS,
  ERROR_HOLD_MS,
  GAZE_RETURN_MS,
  GESTURE_DURATION_MS,
  GLANCE_MOVE_MS,
  IDLE_LIFE_EXPRESSIONS,
  SACCADE_MOVE_MS,
  WAKE_PERFORMANCE,
  WINK_DURATION_MS,
  deriveExpression,
  emoteForExpression,
  gazeHoldMs,
  idleFamilyFor,
  idleGazeTarget,
  inactivityStageFor,
  isDoubleBlink,
  isSillyTime,
  nextBlinkDelayMs,
  nextIdleGestureDelayMs,
  pickIdleFlicker,
  pickIdleGesture,
  pickSillyGesture,
  shouldChainGlance,
  type ExpressionFrame,
  type Gaze,
  type IdleGesture,
  type PerformanceStep,
} from '@/components/eyes/expression-engine';
import { prefersReducedMotion } from '@/lib/utils/motion';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { usePsycheStore } from '@/stores/psycheStore';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import type { ChatState, StreamPhase } from '@/types/chat-state';

const HEARTBEAT_MS = 1000;
const ACTIVITY_EVENTS: ReadonlyArray<keyof WindowEventMap> = [
  'pointerdown',
  'keydown',
  'wheel',
  'touchstart',
];

/**
 * Expression arrivals NOT masked by a transition blink: reflexes (surprise,
 * fear), the wink overlay, and sleep (whose slow lid-fall IS the morph).
 * Everything else gets the animator's classic: blink while the face changes.
 */
const UNMASKED_ARRIVALS: ReadonlySet<string> = new Set(['surprise', 'fear', 'wink', 'sleep']);

export interface EyesBehaviorProps {
  chatStatus: ChatState['status'];
  streamPhase: StreamPhase;
  hitlAwaiting: boolean;
}

export interface UseEyesBehaviorOptions extends EyesBehaviorProps {
  /**
   * False while the widget is minimized: the whole live machinery (heartbeat,
   * store subscriptions, blink chain, activity listeners) stays off — a
   * hidden widget must cost nothing.
   */
  enabled: boolean;
}

/** A wandered idle gaze: the target plus its CSS travel time. */
export interface IdleGazeMove {
  gaze: Gaze;
  ms: number;
}

/** Floating emote lifecycle: glyph plus its leave phase. */
export interface EmoteState {
  glyph: string;
  leaving: boolean;
}

export interface EyesBehavior {
  frame: ExpressionFrame;
  blinking: boolean;
  /** Active idle-life gesture (null between gestures). */
  gesture: IdleGesture | null;
  /** Wandered idle gaze, or null when the eyes rest at center. */
  idleGaze: IdleGazeMove | null;
  /** Floating emote above the eyes, or null. */
  emote: EmoteState | null;
  /** One-shot wink (no-op under reduced motion). */
  wink: () => void;
}

function sameFrame(a: ExpressionFrame, b: ExpressionFrame): boolean {
  return a.expression === b.expression && a.gaze?.x === b.gaze?.x && a.gaze?.y === b.gaze?.y;
}

/**
 * Emote enter/leave transition (module-level: keeps `evaluate` under the CC
 * ratchet). Runs outside render (evaluate is timer/subscription-driven), so
 * mutating the refs and scheduling the exit timer here is legitimate.
 */
function applyEmoteTransition(
  nextEmote: string | null,
  glyphRef: React.MutableRefObject<string | null>,
  timerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | null>,
  setEmote: (value: EmoteState | null) => void
): void {
  if (nextEmote === glyphRef.current) return;
  if (timerRef.current) {
    clearTimeout(timerRef.current);
    timerRef.current = null;
  }
  if (nextEmote) {
    glyphRef.current = nextEmote;
    setEmote({ glyph: nextEmote, leaving: false });
    return;
  }
  const oldGlyph = glyphRef.current;
  glyphRef.current = null;
  if (oldGlyph) {
    setEmote({ glyph: oldGlyph, leaving: true });
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      setEmote(null);
    }, EMOTE_EXIT_MS);
  }
}

export function useEyesBehavior({
  chatStatus,
  streamPhase,
  hitlAwaiting,
  enabled,
}: UseEyesBehaviorOptions): EyesBehavior {
  const [frame, setFrame] = useState<ExpressionFrame>({ expression: 'neutral', gaze: null });
  const [blinking, setBlinking] = useState(false);
  const [winking, setWinking] = useState(false);
  const [gesture, setGesture] = useState<IdleGesture | null>(null);
  const [idleGaze, setIdleGaze] = useState<IdleGazeMove | null>(null);
  // A playing performance (multi-beat scripted sequence) overrides the frame.
  const [performedFrame, setPerformedFrame] = useState<ExpressionFrame | null>(null);
  const performanceTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  // Floating emote: current glyph mirrored in a ref (evaluate runs outside
  // render) so leave transitions schedule exactly one exit timer.
  const [emote, setEmote] = useState<EmoteState | null>(null);
  const emoteGlyphRef = useRef<string | null>(null);
  const emoteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const frameRef = useRef(frame);
  useEffect(() => {
    frameRef.current = frame;
  }, [frame]);
  // Mirrors `winking` for the blink guard: the wink overrides the returned
  // frame but not the `frame` state, so `frameRef` alone cannot see it — and
  // a blink landing mid-wink would visually pop the closed eye back open.
  const winkingRef = useRef(false);
  useEffect(() => {
    winkingRef.current = winking;
  }, [winking]);
  // null = "no activity recorded yet" — stamped at mount by the effect below
  // (a Date.now() initializer would trip the purity ratchet). Without the
  // mount stamp, a user who opens the page and never gestures would read as
  // perpetually active and the eyes would never doze off.
  const lastActivityRef = useRef<number | null>(null);
  useEffect(() => {
    if (lastActivityRef.current === null) lastActivityRef.current = Date.now();
  }, []);
  const erroredAtRef = useRef<number | null>(null);
  const winkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const maskBlinkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Gaze homing timers: every wander MUST come home. These are cleared only
  // at unmount — an enabled-flip (widget minimized mid-glance) must never
  // strand the gaze off-center (owner invariant: no positional drift, ever).
  const gazeHomingTimersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());
  useEffect(() => {
    const timers = gazeHomingTimersRef.current;
    return () => timers.forEach(clearTimeout);
  }, []);

  // A failed turn stays worried for ERROR_HOLD_MS, then eases back to idle
  // even though the reducer keeps status 'error' until the next send. A send
  // is also user activity: it re-arms the dozing-off clock.
  useEffect(() => {
    if (chatStatus === 'error') erroredAtRef.current = Date.now();
    if (chatStatus === 'sending') lastActivityRef.current = Date.now();
  }, [chatStatus]);

  const evaluate = useCallback(() => {
    const now = Date.now();
    const signals = useEyesSignalsStore.getState();
    const psyche = usePsycheStore.getState();
    const voice = useVoiceModeStore.getState();
    const errorExpired =
      erroredAtRef.current !== null && now - erroredAtRef.current >= ERROR_HOLD_MS;
    const next = deriveExpression({
      chatStatus: chatStatus === 'error' && errorExpired ? 'idle' : chatStatus,
      streamPhase,
      lastStepKind: signals.lastStepKind,
      hitlAwaiting,
      voiceState: voice.state,
      reaction: signals.liveReaction(now),
      notificationPing: signals.isNotificationLive(now),
      userTyping: signals.isTypingLive(now),
      moodLabel: psyche.enabled ? psyche.moodLabel : null,
      hourOfDay: new Date().getHours(),
      inactivityStage: inactivityStageFor(now - (lastActivityRef.current ?? now)),
    });
    // Animator's transition trick: blink WHILE the face changes — the lid
    // sweep masks the morph and every switch reads as intentional. Reflexes
    // (see UNMASKED_ARRIVALS) stay raw for impact.
    const changed = next.expression !== frameRef.current.expression;
    if (changed && !UNMASKED_ARRIVALS.has(next.expression) && !prefersReducedMotion()) {
      setBlinking(true);
      if (maskBlinkTimerRef.current) clearTimeout(maskBlinkTimerRef.current);
      maskBlinkTimerRef.current = setTimeout(() => setBlinking(false), BLINK_DURATION_MS);
    }
    setFrame(prev => (sameFrame(prev, next) ? prev : next));
    // Floating emote lifecycle: enter on a mapped expression, animated leave
    // (EMOTE_EXIT_MS) when the mapping goes away.
    applyEmoteTransition(
      emoteForExpression(next.expression),
      emoteGlyphRef,
      emoteTimerRef,
      setEmote
    );
    // Leaving the wandering family cancels the idle life immediately — a
    // directed expression must never carry a stale wander target or gesture.
    // 'speaking' keeps its gaze wander (eyes move while talking) but never
    // plays one-shot gestures (see the idle-life loop).
    if (!IDLE_LIFE_EXPRESSIONS.has(next.expression) && next.expression !== 'speaking') {
      setIdleGaze(prev => (prev === null ? prev : null));
      setGesture(prev => (prev === null ? prev : null));
    }
  }, [chatStatus, streamPhase, hitlAwaiting]);

  // Re-derive on every input change: props (via evaluate identity), the three
  // live stores, and the heartbeat that ages the time-based signals. The
  // initial derivation is SCHEDULED (0 ms) rather than called synchronously —
  // a sync setState in an effect trips the shrink-only react-hooks ratchet.
  useEffect(() => {
    if (!enabled) return;
    const initialId = setTimeout(evaluate, 0);
    const unsubscribes = [
      useEyesSignalsStore.subscribe(evaluate),
      usePsycheStore.subscribe(evaluate),
      useVoiceModeStore.subscribe(evaluate),
    ];
    return () => {
      clearTimeout(initialId);
      unsubscribes.forEach(unsubscribe => unsubscribe());
    };
  }, [evaluate, enabled]);

  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => {
      if (!document.hidden) evaluate();
    }, HEARTBEAT_MS);
    return () => clearInterval(id);
  }, [evaluate, enabled]);

  /** Play a scripted multi-beat sequence (replaces any running one). */
  const playPerformance = useCallback((steps: readonly PerformanceStep[]) => {
    if (prefersReducedMotion()) return;
    performanceTimersRef.current.forEach(clearTimeout);
    performanceTimersRef.current = [];
    let at = 0;
    for (const step of steps) {
      performanceTimersRef.current.push(
        setTimeout(() => setPerformedFrame({ expression: step.expression, gaze: step.gaze }), at)
      );
      at += step.ms;
    }
    performanceTimersRef.current.push(setTimeout(() => setPerformedFrame(null), at));
  }, []);

  useEffect(() => {
    return () => {
      performanceTimersRef.current.forEach(clearTimeout);
    };
  }, []);

  // Dozing-off clock: any user gesture re-arms it (passive, cheap). Activity
  // landing on dozing eyes plays the wake startle — a character wakes with a
  // jolt and a look around, never a fade.
  useEffect(() => {
    if (!enabled) return;
    const touch = () => {
      const wasDozing =
        frameRef.current.expression === 'sleep' || frameRef.current.expression === 'sleepy';
      lastActivityRef.current = Date.now();
      if (wasDozing) playPerformance(WAKE_PERFORMANCE);
    };
    ACTIVITY_EVENTS.forEach(event => window.addEventListener(event, touch, { passive: true }));
    return () => ACTIVITY_EVENTS.forEach(event => window.removeEventListener(event, touch));
  }, [enabled, playPerformance]);

  // Spontaneous blinks. Self-rescheduling timeout chain; only PENDING timers
  // are tracked (fired ones remove themselves), so a day-long session never
  // accumulates dead handles, and unmount clears exactly what is live.
  useEffect(() => {
    if (!enabled || prefersReducedMotion()) return;
    let cancelled = false;
    const pending = new Set<ReturnType<typeof setTimeout>>();
    const after = (ms: number, fn: () => void) => {
      const id = setTimeout(() => {
        pending.delete(id);
        fn();
      }, ms);
      pending.add(id);
    };
    const runBlink = () => {
      setBlinking(true);
      after(BLINK_DURATION_MS, () => setBlinking(false));
    };
    const schedule = () => {
      after(nextBlinkDelayMs(Math.random), () => {
        if (cancelled) return;
        const expression = frameRef.current.expression;
        const canBlink = !document.hidden && !winkingRef.current && expression !== 'sleep';
        if (canBlink) {
          runBlink();
          if (isDoubleBlink(Math.random)) {
            after(BLINK_DURATION_MS + DOUBLE_BLINK_GAP_MS, runBlink);
          }
        }
        schedule();
      });
    };
    schedule();
    return () => {
      cancelled = true;
      pending.forEach(clearTimeout);
    };
  }, [enabled]);

  // Idle life: the random gesture loop that keeps the eyes alive between
  // events — gaze wander (saccades/glances with hold-and-return) and one-shot
  // gestures, weighted by the current mood family. Same pending-timer
  // discipline as the blink chain.
  useEffect(() => {
    if (!enabled || prefersReducedMotion()) return;
    let cancelled = false;
    const pending = new Set<ReturnType<typeof setTimeout>>();
    const after = (ms: number, fn: () => void) => {
      const id = setTimeout(() => {
        pending.delete(id);
        fn();
      }, ms);
      pending.add(id);
    };
    // Homing scheduler: NOT tracked in `pending` on purpose — a wander whose
    // loop gets torn down (widget minimized, expression flip) must still
    // complete its trip home. Cleared only at hook unmount.
    const scheduleGazeMove = (atMs: number, move: IdleGazeMove) => {
      const id = setTimeout(() => {
        gazeHomingTimersRef.current.delete(id);
        setIdleGaze(prev => (prev === null ? prev : move));
      }, atMs);
      gazeHomingTimersRef.current.add(id);
    };
    const playGazeWander = (kind: 'saccade' | 'glance') => {
      const target = idleGazeTarget(Math.random, kind);
      setIdleGaze({ gaze: target, ms: kind === 'saccade' ? SACCADE_MOVE_MS : GLANCE_MOVE_MS });
      const holdMs = gazeHoldMs(Math.random, kind);
      const home: IdleGazeMove = { gaze: { x: 0, y: 0 }, ms: GAZE_RETURN_MS };
      // Composite beat: a glance sometimes sweeps to the OTHER side before
      // coming home — the "scanning the room" performance. Every branch ends
      // scheduled-home: the gaze can never be stranded off-center.
      if (kind === 'glance' && shouldChainGlance(Math.random)) {
        scheduleGazeMove(holdMs, {
          gaze: { x: -target.x, y: target.y * 0.6 },
          ms: GLANCE_MOVE_MS,
        });
        scheduleGazeMove(holdMs + gazeHoldMs(Math.random, 'glance'), home);
      } else {
        scheduleGazeMove(holdMs, home);
      }
    };
    const loop = () => {
      after(nextIdleGestureDelayMs(Math.random), () => {
        if (cancelled) return;
        const current = frameRef.current;
        // 'speaking' wanders too — eyes move while talking (a metronomic bob
        // alone reads as robotic) — but only saccades, never posed gestures.
        const speaking = current.expression === 'speaking';
        const alive =
          !document.hidden &&
          !winkingRef.current &&
          current.gaze === null &&
          (speaking || IDLE_LIFE_EXPRESSIONS.has(current.expression));
        if (alive) {
          if (speaking) {
            playGazeWander('saccade');
          } else if (idleFamilyFor(current.expression) !== 'drowsy' && isSillyTime(Math.random)) {
            // Rare slapstick beat — comedy needs an awake face.
            const silly = pickSillyGesture(Math.random);
            setGesture(silly);
            after(GESTURE_DURATION_MS[silly], () => setGesture(null));
          } else {
            const picked = pickIdleGesture(Math.random, current.expression);
            if (picked === 'saccade' || picked === 'glance') {
              playGazeWander(picked);
            } else if (picked === 'flicker') {
              // Mini mood scene — rides the performance channel.
              playPerformance(pickIdleFlicker(Math.random));
            } else {
              setGesture(picked);
              after(GESTURE_DURATION_MS[picked], () => setGesture(null));
            }
          }
        }
        loop();
      });
    };
    loop();
    return () => {
      cancelled = true;
      pending.forEach(clearTimeout);
    };
  }, [enabled, playPerformance]);

  const wink = useCallback(() => {
    if (prefersReducedMotion()) return;
    setWinking(true);
    if (winkTimerRef.current) clearTimeout(winkTimerRef.current);
    winkTimerRef.current = setTimeout(() => setWinking(false), WINK_DURATION_MS);
  }, []);

  useEffect(() => {
    // Timer handles (not DOM nodes): reading them at cleanup time is the
    // point — the array indirection keeps exhaustive-deps quiet about it.
    const timerRefs = [winkTimerRef, maskBlinkTimerRef, emoteTimerRef];
    return () => {
      timerRefs.forEach(ref => {
        if (ref.current) clearTimeout(ref.current);
      });
    };
  }, []);

  return {
    // Overlay priority: the wink beats a performance beats the derived frame.
    frame: winking ? { expression: 'wink', gaze: null } : (performedFrame ?? frame),
    blinking,
    gesture,
    idleGaze,
    emote,
    wink,
  };
}

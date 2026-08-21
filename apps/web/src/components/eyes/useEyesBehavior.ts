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
  MASK_APPLY_DELAY_MS,
  MIN_EXPRESSION_HOLD_MS,
  PRE_GAZE_BLINK_LEAD_MS,
  READING_STEP_MS,
  RETURN_PERK_MIN_AWAY_MS,
  SACCADE_MOVE_MS,
  URGENT_ARRIVALS,
  WINK_DURATION_MS,
  WONDER_PERFORMANCE,
  deriveExpression,
  emoteForExpression,
  gazeHoldMs,
  resolveIdleFamily,
  idleGazeTarget,
  inactivityStageFor,
  isDoubleBlink,
  isSillyTime,
  moodShiftPerformance,
  nextBlinkDelayMs,
  nextIdleGestureDelayMs,
  pickIdleFlicker,
  pickIdleGesture,
  pickSillyGesture,
  readingGazeAt,
  shouldBlinkBeforeGaze,
  shouldChainGlance,
  wakePerformanceFor,
  type ExpressionFrame,
  type EyeExpression,
  type Gaze,
  type IdleGesture,
  type IdleMoodFamily,
  type PerformanceStep,
} from '@/components/eyes/expression-engine';
import type { MoodLabel } from '@/types/psyche';
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
  /** Idle mood family pacing breathing and blink cadence. */
  family: IdleMoodFamily;
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
 * Sleep clock for the proportional wake: stamped when 'sleep' lands, kept
 * through the sleepy hysteresis, cleared on any awake expression. touch()
 * reads it BEFORE the heartbeat re-derives a woken expression and clears it.
 */
function trackSleepClock(
  expression: EyeExpression,
  now: number,
  sleepSinceRef: React.MutableRefObject<number | null>
): void {
  if (expression === 'sleep') {
    sleepSinceRef.current ??= now;
  } else if (expression !== 'sleepy') {
    sleepSinceRef.current = null;
  }
}

/**
 * Narrative beats on signal EDGES (module-level: keeps `evaluate` under the
 * CC ratchet): a cross-family mood shift plays its rise/fall beat, a typing
 * signal that expires without a send plays the "you were saying?" wonder.
 * Also advances the edge-tracking refs — call exactly once per evaluation.
 */
function runNarrativeBeats(
  current: { idleStage: boolean; mood: MoodLabel | null; typingNow: boolean },
  refs: {
    prevMoodRef: React.MutableRefObject<MoodLabel | null>;
    typingWasRef: React.MutableRefObject<boolean>;
  },
  playPerformance: (steps: readonly PerformanceStep[]) => void
): void {
  const { idleStage, mood, typingNow } = current;
  const prevMood = refs.prevMoodRef.current;
  if (idleStage && prevMood && mood && prevMood !== mood) {
    const beat = moodShiftPerformance(prevMood, mood);
    if (beat) playPerformance(beat);
  }
  if (idleStage && refs.typingWasRef.current && !typingNow) {
    playPerformance(WONDER_PERFORMANCE);
  }
  refs.prevMoodRef.current = mood;
  refs.typingWasRef.current = typingNow;
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
  const [family, setFamily] = useState<IdleMoodFamily>('calm');
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
  // Single blink-off timer shared by ALL blink sources (spontaneous chain,
  // pre-gaze blink, transition mask): the last pulse wins. Independent off
  // timers could clear `is-blinking` mid-cycle of a concurrent pulse — the
  // lid animation would cut and snap open without a transition.
  const blinkPulseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pulseBlink = useCallback(() => {
    setBlinking(true);
    if (blinkPulseTimerRef.current) clearTimeout(blinkPulseTimerRef.current);
    blinkPulseTimerRef.current = setTimeout(() => setBlinking(false), BLINK_DURATION_MS);
  }, []);
  useEffect(() => {
    return () => {
      if (blinkPulseTimerRef.current) clearTimeout(blinkPulseTimerRef.current);
    };
  }, []);
  // Transition grammar state: minimum-hold clock, masked-swap timer, and the
  // previous mood/typing signals whose EDGES trigger narrative beats.
  const familyRef = useRef<IdleMoodFamily>('calm');
  const heldSinceRef = useRef(0);
  const pendingFrameTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const holdRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevMoodRef = useRef<MoodLabel | null>(null);
  const typingWasRef = useRef(false);
  const sleepSinceRef = useRef<number | null>(null);
  const hiddenAtRef = useRef<number | null>(null);
  const returnPerkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
      if (pendingFrameTimerRef.current) clearTimeout(pendingFrameTimerRef.current);
      if (holdRetryTimerRef.current) clearTimeout(holdRetryTimerRef.current);
      if (returnPerkTimerRef.current) clearTimeout(returnPerkTimerRef.current);
    };
  }, []);
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
    performanceTimersRef.current.push(
      setTimeout(() => {
        // Also empties the timer list so cancelPerformance() stays a true
        // no-op between performances (it runs on every interactive evaluate).
        performanceTimersRef.current = [];
        setPerformedFrame(null);
      }, at)
    );
  }, []);

  /** Cut a running performance short (an interactive state took the stage). */
  const cancelPerformance = useCallback(() => {
    if (performanceTimersRef.current.length === 0) return;
    performanceTimersRef.current.forEach(clearTimeout);
    performanceTimersRef.current = [];
    setPerformedFrame(null);
  }, []);

  // Evaluate is re-entrant through the hold-retry timer; the ref avoids a
  // circular useCallback dependency between applyFrame and evaluate.
  const evaluateRef = useRef<() => void>(() => {});

  /**
   * Land a derived frame with the transition grammar: a non-urgent expression
   * holds MIN_EXPRESSION_HOLD_MS before being replaced (anti-zapping), and a
   * masked change swaps the face at the TOP of the lid sweep (three-beat:
   * blink, swap out of sight, reveal) instead of morphing in plain view.
   */
  const applyFrame = useCallback(
    (next: ExpressionFrame, now: number) => {
      const changed = next.expression !== frameRef.current.expression;
      if (changed) {
        const heldFor = now - heldSinceRef.current;
        if (heldFor < MIN_EXPRESSION_HOLD_MS && !URGENT_ARRIVALS.has(next.expression)) {
          if (holdRetryTimerRef.current) clearTimeout(holdRetryTimerRef.current);
          holdRetryTimerRef.current = setTimeout(
            () => evaluateRef.current(),
            MIN_EXPRESSION_HOLD_MS - heldFor
          );
          return;
        }
        heldSinceRef.current = now;
      }
      const land = () => {
        setFrame(prev => (sameFrame(prev, next) ? prev : next));
        applyEmoteTransition(
          emoteForExpression(next.expression),
          emoteGlyphRef,
          emoteTimerRef,
          setEmote
        );
        // Leaving the wandering family cancels the idle life immediately — a
        // directed expression must never carry a stale wander target or
        // gesture. 'speaking' keeps its reading-gaze loop but never plays
        // one-shot gestures (see the idle-life loop).
        if (!IDLE_LIFE_EXPRESSIONS.has(next.expression) && next.expression !== 'speaking') {
          setIdleGaze(prev => (prev === null ? prev : null));
          setGesture(prev => (prev === null ? prev : null));
        }
      };
      if (pendingFrameTimerRef.current) {
        clearTimeout(pendingFrameTimerRef.current);
        pendingFrameTimerRef.current = null;
      }
      if (changed && !UNMASKED_ARRIVALS.has(next.expression) && !prefersReducedMotion()) {
        pulseBlink();
        pendingFrameTimerRef.current = setTimeout(() => {
          pendingFrameTimerRef.current = null;
          land();
        }, MASK_APPLY_DELAY_MS);
        return;
      }
      land();
    },
    [pulseBlink]
  );

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
    // Mood family: the personality channel (breathing pace, blink cadence,
    // gesture weights) — tracked as state for CSS and a ref for the timers.
    const mood = psyche.enabled ? psyche.moodLabel : null;
    const nextFamily = resolveIdleFamily(mood, next.expression);
    familyRef.current = nextFamily;
    setFamily(prev => (prev === nextFamily ? prev : nextFamily));
    trackSleepClock(next.expression, now, sleepSinceRef);
    // Narrative beats on signal EDGES, idle-stage only (an interactive state
    // owns the face): a cross-family mood shift plays its rise/fall beat; a
    // typing signal that expires without a send plays the "you were
    // saying?" wonder.
    const idleStage = chatStatus === 'idle' && !hitlAwaiting && voice.state !== 'speaking';
    const typingNow = signals.isTypingLive(now);
    runNarrativeBeats(
      { idleStage, mood, typingNow },
      { prevMoodRef, typingWasRef },
      playPerformance
    );
    // An interactive state — or a live notification ping — cuts any playing
    // performance short: the beats are idle storytelling, never allowed to
    // sit on top of a live exchange or to hide the notification glance.
    if (!idleStage || signals.isNotificationLive(now)) cancelPerformance();
    applyFrame(next, now);
  }, [chatStatus, streamPhase, hitlAwaiting, playPerformance, cancelPerformance, applyFrame]);
  useEffect(() => {
    evaluateRef.current = evaluate;
  }, [evaluate]);

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
      const sleptMs = sleepSinceRef.current ? Date.now() - sleepSinceRef.current : 0;
      lastActivityRef.current = Date.now();
      // Proportional wake: a short nap earns a quick recollection, deep
      // sleep the full startle — the reaction tells how long the eyes slept.
      if (wasDozing) playPerformance(wakePerformanceFor(sleptMs));
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
    const runBlink = () => pulseBlink();
    const schedule = () => {
      after(nextBlinkDelayMs(Math.random, familyRef.current), () => {
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
  }, [enabled, pulseBlink]);

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
      const start = () => {
        const target = idleGazeTarget(Math.random, kind);
        setIdleGaze({ gaze: target, ms: kind === 'saccade' ? SACCADE_MOVE_MS : GLANCE_MOVE_MS });
        const holdMs = gazeHoldMs(Math.random, kind);
        const home: IdleGazeMove = { gaze: { x: 0, y: 0 }, ms: GAZE_RETURN_MS };
        // Composite beat: a glance sometimes sweeps to the OTHER side before
        // coming home — the "scanning the room" performance. Every branch
        // ends scheduled-home: the gaze can never be stranded off-center.
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
      // Cognitive-boundary blink: a fraction of wanders opens with a blink
      // whose lid covers the saccade start — the move reads as intentional.
      if (shouldBlinkBeforeGaze(Math.random)) {
        pulseBlink();
        after(PRE_GAZE_BLINK_LEAD_MS, start);
      } else {
        start();
      }
    };
    const loop = () => {
      after(nextIdleGestureDelayMs(Math.random), () => {
        if (cancelled) return;
        const current = frameRef.current;
        // 'speaking' lives in its own reading loop (below), not here.
        const alive =
          !document.hidden &&
          !winkingRef.current &&
          current.gaze === null &&
          IDLE_LIFE_EXPRESSIONS.has(current.expression);
        if (alive) {
          // The mood is the personality channel of the idle life (soft
          // resting poses carry none) — read fresh at each tick.
          const psyche = usePsycheStore.getState();
          const family = resolveIdleFamily(
            psyche.enabled ? psyche.moodLabel : null,
            current.expression
          );
          if (family !== 'drowsy' && isSillyTime(Math.random)) {
            // Rare slapstick beat — comedy needs an awake face.
            const silly = pickSillyGesture(Math.random);
            setGesture(silly);
            after(GESTURE_DURATION_MS[silly], () => setGesture(null));
          } else {
            const picked = pickIdleGesture(Math.random, family);
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
  }, [enabled, playPerformance, pulseBlink]);

  // Reading loop: while the answer streams ('speaking'), the gaze walks a
  // reading line in small left-to-right steps with a quick carriage return —
  // the eyes "write" their answer. Replaces random saccades for this state;
  // when speaking ends the last beat sends the gaze home.
  useEffect(() => {
    if (!enabled || prefersReducedMotion()) return;
    let cancelled = false;
    let step = 1;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = () => {
      timer = setTimeout(() => {
        if (cancelled) return;
        const speaking = frameRef.current.expression === 'speaking';
        if (speaking && !document.hidden && !winkingRef.current) {
          const move = readingGazeAt(step);
          setIdleGaze({ gaze: move.gaze, ms: move.ms });
          step += 1;
        } else if (step > 1) {
          // Left mid-line: come home, never strand the gaze off-center.
          setIdleGaze(prev =>
            prev === null ? prev : { gaze: { x: 0, y: 0 }, ms: GAZE_RETURN_MS }
          );
          step = 1;
        }
        tick();
      }, READING_STEP_MS);
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      // Torn down mid-line (widget minimized while streaming): send the gaze
      // home NOW — the loop is gone, nobody else would (owner invariant: no
      // positional drift, ever — same rule as gazeHomingTimersRef).
      if (step > 1) {
        setIdleGaze(prev => (prev === null ? prev : { gaze: { x: 0, y: 0 }, ms: GAZE_RETURN_MS }));
      }
    };
  }, [enabled]);

  // Coming back to the tab after a real absence earns a small welcome perk —
  // awake families only (a drowsy character does not jump to attention).
  useEffect(() => {
    if (!enabled) return;
    const onVisibility = () => {
      if (document.hidden) {
        hiddenAtRef.current = Date.now();
        return;
      }
      const awayMs = hiddenAtRef.current ? Date.now() - hiddenAtRef.current : 0;
      hiddenAtRef.current = null;
      const welcoming =
        awayMs >= RETURN_PERK_MIN_AWAY_MS &&
        familyRef.current !== 'drowsy' &&
        IDLE_LIFE_EXPRESSIONS.has(frameRef.current.expression) &&
        !prefersReducedMotion();
      if (welcoming) {
        setGesture('perk');
        if (returnPerkTimerRef.current) clearTimeout(returnPerkTimerRef.current);
        returnPerkTimerRef.current = setTimeout(() => setGesture(null), GESTURE_DURATION_MS.perk);
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [enabled]);

  const wink = useCallback(() => {
    if (prefersReducedMotion()) return;
    setWinking(true);
    if (winkTimerRef.current) clearTimeout(winkTimerRef.current);
    winkTimerRef.current = setTimeout(() => setWinking(false), WINK_DURATION_MS);
  }, []);

  useEffect(() => {
    // Timer handles (not DOM nodes): reading them at cleanup time is the
    // point — the array indirection keeps exhaustive-deps quiet about it.
    const timerRefs = [winkTimerRef, emoteTimerRef];
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
    family,
    gesture,
    idleGaze,
    emote,
    wink,
  };
}

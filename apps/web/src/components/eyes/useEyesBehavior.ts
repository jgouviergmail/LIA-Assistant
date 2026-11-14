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

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

import {
  BLINK_DURATION_MS,
  DOUBLE_BLINK_GAP_MS,
  EMOTE_EXIT_MS,
  ERROR_HOLD_MS,
  GAZE_RETURN_MS,
  GESTURE_DURATION_MS,
  GLANCE_MOVE_MS,
  IDLE_LIFE_EXPRESSIONS,
  MIN_EXPRESSION_HOLD_MS,
  PRE_GAZE_BLINK_LEAD_MS,
  RETURN_PERK_MIN_AWAY_MS,
  SACCADE_MOVE_MS,
  URGENT_ARRIVALS,
  WINK_DURATION_MS,
  deriveExpression,
  sleepPolicyFrame,
  accessoryForExpression,
  frameEmote,
  gazeHoldMs,
  resolveIdleFamily,
  idleGazeTarget,
  inactivityStageFor,
  isDoubleBlink,
  nextBlinkDelayMs,
  nextIdleGestureDelayMs,
  pickIdleGesture,
  shouldBlinkBeforeGaze,
  shouldChainGlance,
  wakePerformanceFor,
  ACCESSORY_DURATION_MS,
  type EyeAccessory,
  type ExpressionFrame,
  type EyeExpression,
  type Gaze,
  type IdleGesture,
  type IdleMoodFamily,
  type PerformanceStep,
} from '@/components/eyes/expression-engine';
import { accentSparkles, deliveryGesture, type ToneAccent } from '@/components/eyes/tone';
import {
  ACKNOWLEDGEMENT_GESTURE,
  HAND_OVER_AFTER_MS,
  HAND_OVER_GESTURE,
  TOOL_DONE_GESTURE,
  finishedToolKey,
  handsOver,
  mayHandOver,
  messageSent,
} from '@/components/eyes/exchange-beats';
import { prefersReducedMotion } from '@/lib/utils/motion';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { usePsycheStore } from '@/stores/psycheStore';
import { useCompanionEnvironmentStore } from '@/stores/companionEnvironmentStore';
import { readCompanionSignals } from './behavior-context';
import { useLiveStore } from '@/stores/liveStore';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import type { ChatState, StreamPhase } from '@/types/chat-state';

function subscribeMotion(listener: () => void): () => void {
  const query = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  query?.addEventListener('change', listener);
  return () => query?.removeEventListener('change', listener);
}

const HEARTBEAT_MS = 1000;
const ACTIVITY_EVENTS: ReadonlyArray<keyof WindowEventMap> = [
  'pointerdown',
  'keydown',
  'wheel',
  'touchstart',
];

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
  /** Public presentations stay awake; application companions may doze by default. */
  allowSleep?: boolean;
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
  /** Compatibility with explicit rig performances; natural transitions never mask. */
  blinkMask: boolean;
  /** Idle mood family pacing breathing and blink cadence. */
  family: IdleMoodFamily;
  /** Active idle-life gesture (null between gestures). */
  gesture: IdleGesture | null;
  /** Wandered idle gaze, or null when the eyes rest at center. */
  idleGaze: IdleGazeMove | null;
  /** Floating emote above the eyes, or null. */
  emote: EmoteState | null;
  /** Rare one-shot cartoon accessory (a tear, a bead of sweat, a spark). */
  accessory: EyeAccessory | null;
  /** How forcefully the last answer was written, while its reaction is
   * held; 1 the rest of the time. Scales the pose, never picks it. */
  emphasis: number;
  responseWeight: number;
  /** One-shot wink (no-op under reduced motion). */
  wink: () => void;
}

function sameFrame(a: ExpressionFrame, b: ExpressionFrame): boolean {
  return (
    a.expression === b.expression &&
    a.target === b.target &&
    a.gaze?.x === b.gaze?.x &&
    a.gaze?.y === b.gaze?.y
  );
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

/**
 * Roll for the accessory an arriving expression brings with it.
 *
 * Module-level for the same reason as the emote transition: `evaluate` is
 * timer-driven, not render-driven, and keeping the body out of it is what
 * holds the hook under the complexity ratchet. Reduced motion declines the
 * roll outright — an accessory is pure flourish, and a flourish is the first
 * thing that preference asks to be spared.
 */
/** How long a declared accent beat plays before the face lets it go. */
const ACCENT_BEAT_MS = 900;

type TimerRef = React.MutableRefObject<ReturnType<typeof setTimeout> | null>;
type SignalsState = ReturnType<typeof useEyesSignalsStore.getState>;

/** The timers the delivery of an answer keeps between two evaluations. */
interface DeliveryTimers {
  readonly beat: TimerRef;
  readonly handOver: TimerRef;
}

/** The beat a delivered answer earned, waiting for the answer's own face. */
interface PendingDelivery {
  readonly gesture: IdleGesture;
  /** The face the answer earned: the beat plays on the frame that lands it. */
  readonly expression: EyeExpression;
  /** The reaction it belongs to; another one, or none, cancels it. */
  readonly at: number;
}

function cancelHandOver(handOver: TimerRef): void {
  if (handOver.current) clearTimeout(handOver.current);
  handOver.current = null;
}

/**
 * Read what a delivered answer earned (ADR-253, ADR-294): the accent its
 * model declared when it declared a movement, the register's presentation
 * when it declared none (`deliveryGesture`). Returns the accent, which the
 * arriving frame's accessory reads, and the beat, PARKED like that accessory
 * for the frame that lands the answer's face: played before it, the beat was
 * wiped a commit later by that very arrival (the rig interrupts every beat
 * on a new expression), so a streamed answer was never presented at all.
 */
function receiveAnswer(
  signals: SignalsState,
  now: number,
  handOver: TimerRef
): { accent: ToneAccent; delivery: PendingDelivery | null } {
  cancelHandOver(handOver);
  const reaction = signals.reaction;
  const accent = signals.liveAccent(now);
  if (!reaction || !signals.isReactionHeld(now)) return { accent, delivery: null };
  const gesture = deliveryGesture(reaction.expression, accent);
  return {
    accent,
    delivery: gesture ? { gesture, expression: reaction.expression, at: reaction.at } : null,
  };
}

/**
 * Play the parked delivery on the frame that lands its answer's face — the
 * same commit, so the arrival comes first and cannot wipe it — then, after a
 * presentation, the hand-over a moment later, « à toi », if it is still owed
 * when its time comes.
 *
 * Kept module-level next to `applyAccessory`, for the same two reasons: it
 * holds the hook under the complexity ratchet, and reduced motion declines
 * every beat outright (`playBeat`) — a delivery is punctuation on an
 * expression, and the expression says the same thing without it. `sparkle`
 * is an accessory, not a movement: `applyAccessory` owns it.
 */
function deliverOnArrival(
  expression: EyeExpression,
  now: number,
  pending: React.MutableRefObject<PendingDelivery | null>,
  timers: DeliveryTimers,
  setBeat: (value: IdleGesture | null) => void
): void {
  // A face that speaks plays no delivery: the voice hands the answer over itself.
  // A presentation under way, or the « à toi » falling due three seconds later,
  // played on through the first words and moved a mouth the voice was to move
  // (owner report 2026-11-14, spoken comments and both Live modes). The delivery
  // still parked goes too: played when the voice pauses between two phrases, it
  // would be cut by the next one.
  if (expression === 'speaking') {
    pending.current = null;
    cancelHandOver(timers.handOver);
    playBeat(null, 0, timers.beat, setBeat);
    return;
  }
  const delivery = pending.current;
  if (!delivery || delivery.expression !== expression) return;
  pending.current = null;
  const signals = useEyesSignalsStore.getState();
  if (signals.reaction?.at !== delivery.at || !signals.isReactionHeld(now)) return;
  const { gesture } = delivery;
  if (!handsOver(gesture)) {
    playBeat(gesture, ACCENT_BEAT_MS, timers.beat, setBeat);
    return;
  }
  playBeat(gesture, GESTURE_DURATION_MS[gesture], timers.beat, setBeat);
  timers.handOver.current = setTimeout(() => {
    timers.handOver.current = null;
    const current = useEyesSignalsStore.getState();
    const heldAt = current.reaction?.at ?? null;
    if (!mayHandOver(heldAt, delivery.at, current.isAttending(Date.now()))) return;
    playBeat(HAND_OVER_GESTURE, GESTURE_DURATION_MS[HAND_OVER_GESTURE], timers.beat, setBeat);
  }, HAND_OVER_AFTER_MS);
}

/**
 * Whether something else owns the face, so its idle life waits: real work, an
 * answer it holds, or a beat the exchange earned that is still playing — a
 * wandering look in the middle of « à toi » would take back what it hands over.
 */
function faceIsTaken(signals: SignalsState, now: number, beat: IdleGesture | null): boolean {
  return Boolean(signals.liveActivity(now)) || signals.isReactionHeld(now) || beat !== null;
}

/**
 * Play ONE beat and let it go once it has played — the single channel for
 * everything the exchange earns from the face: an answer's accent, the
 * acknowledgement of a message, the mark of a finished tool. The last one
 * asked wins; reduced motion declines them all.
 */
function playBeat(
  gesture: IdleGesture | null,
  holdMs: number,
  beatTimerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | null>,
  setBeat: (value: IdleGesture | null) => void
): void {
  if (beatTimerRef.current) {
    clearTimeout(beatTimerRef.current);
    beatTimerRef.current = null;
  }
  const beat = prefersReducedMotion() ? null : gesture;
  setBeat(beat);
  if (!beat) return;
  beatTimerRef.current = setTimeout(() => {
    beatTimerRef.current = null;
    setBeat(null);
  }, holdMs);
}

/** What the exchange's beats read and write between two evaluations. */
interface ExchangeBeatState {
  /** The chat status the previous evaluation saw. */
  status: React.MutableRefObject<ChatState['status']>;
  /** The finished tool already marked; `undefined` until the face has looked
   * once — what finished before it was mounted is not its to mark. */
  markedTool: React.MutableRefObject<string | null | undefined>;
  /** When the current expression landed: an acknowledgement re-arms the hold,
   * so the thought that follows a send waits for the beat instead of cutting it. */
  heldSince: React.MutableRefObject<number>;
  beatTimer: React.MutableRefObject<ReturnType<typeof setTimeout> | null>;
  setBeat: (value: IdleGesture | null) => void;
  pulseBlink: () => void;
}

/**
 * The beats of a turn under way, on signal EDGES (`exchange-beats.ts`): a
 * message leaves, a tool comes back with a result.
 *
 * Module-level for the reason the accent is: `evaluate` is timer-driven and
 * sits under the complexity ratchet.
 */
function playExchangeBeats(
  chatStatus: ChatState['status'],
  finishedTool: string | null,
  now: number,
  state: ExchangeBeatState
): void {
  const sent = messageSent(state.status.current, chatStatus);
  state.status.current = chatStatus;
  const marked = state.markedTool.current;
  state.markedTool.current = finishedTool;
  if (prefersReducedMotion()) return;
  if (sent) {
    state.heldSince.current = now;
    playBeat(
      ACKNOWLEDGEMENT_GESTURE,
      GESTURE_DURATION_MS[ACKNOWLEDGEMENT_GESTURE],
      state.beatTimer,
      state.setBeat
    );
    return;
  }
  if (marked === undefined || finishedTool === null || finishedTool === marked) return;
  // A boundary of attention is a blink; the brows say what it found.
  state.pulseBlink();
  playBeat(
    TOOL_DONE_GESTURE,
    GESTURE_DURATION_MS[TOOL_DONE_GESTURE],
    state.beatTimer,
    state.setBeat
  );
}

function showAccessory(
  next: EyeAccessory | null,
  timerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | null>,
  setAccessory: (value: EyeAccessory | null) => void
): void {
  if (timerRef.current) {
    clearTimeout(timerRef.current);
    timerRef.current = null;
  }
  setAccessory(next);
  if (!next) return;
  timerRef.current = setTimeout(() => {
    timerRef.current = null;
    setAccessory(null);
  }, ACCESSORY_DURATION_MS[next]);
}

function applyAccessory(
  expression: EyeExpression,
  accent: ToneAccent,
  timerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | null>,
  setAccessory: (value: EyeAccessory | null) => void
): void {
  if (prefersReducedMotion()) {
    showAccessory(null, timerRef, setAccessory);
    return;
  }
  // The accent WINS over the roll. It is an explicit statement about the answer
  // that just landed, where the roll is a rare flourish the expression may or
  // may not earn — and resolving both here is what keeps one accessory to one
  // owner. Written as two writers, the arrival's roll silently overwrote the
  // accent a few milliseconds after it was set.
  const earned = accentSparkles(accent) ? 'sparkle' : null;
  showAccessory(earned ?? accessoryForExpression(expression, Math.random), timerRef, setAccessory);
}

export function useEyesBehavior({
  chatStatus,
  streamPhase,
  hitlAwaiting,
  enabled,
  allowSleep,
}: UseEyesBehaviorOptions): EyesBehavior {
  const motionReduced = useSyncExternalStore(subscribeMotion, prefersReducedMotion, () => false);
  const [frame, setFrame] = useState<ExpressionFrame>({
    expression: 'neutral',
    gaze: null,
  });
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
  const [accessory, setAccessory] = useState<EyeAccessory | null>(null);
  const [emphasis, setEmphasis] = useState(1);
  const [responseWeight, setResponseWeight] = useState(1);
  // The one-shot beat the EXCHANGE earned: an answer's accent, the
  // acknowledgement of a message, the mark of a finished tool. Held apart
  // from the idle gesture because the two have different owners and
  // different lifetimes: an idle gesture is cleared the moment a directed
  // expression arrives, which is exactly when a beat is supposed to play.
  const [accentBeat, setAccentBeatState] = useState<IdleGesture | null>(null);
  const accentTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handOverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingDeliveryRef = useRef<PendingDelivery | null>(null);
  // The idle-life timers read the beat outside render: the ref changes in
  // the same call as the state, never one commit later.
  const accentBeatRef = useRef<IdleGesture | null>(null);
  const setAccentBeat = useCallback((beat: IdleGesture | null) => {
    accentBeatRef.current = beat;
    setAccentBeatState(beat);
  }, []);
  const beatStatusRef = useRef(chatStatus);
  const markedToolRef = useRef<string | null | undefined>(undefined);
  const lastReactionAtRef = useRef<number | null>(null);
  const pendingAccentRef = useRef<ToneAccent>('none');
  const accessoryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
  // pre-gaze blink): the last pulse wins. Independent off
  // timers could clear `is-blinking` mid-cycle of a concurrent pulse — the
  // lid animation would cut and snap open without a transition.
  const blinkPulseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pulseBlink = useCallback(() => {
    setBlinking(true);
    if (blinkPulseTimerRef.current) clearTimeout(blinkPulseTimerRef.current);
    blinkPulseTimerRef.current = setTimeout(() => {
      setBlinking(false);
    }, BLINK_DURATION_MS);
  }, []);
  useEffect(() => {
    return () => {
      if (blinkPulseTimerRef.current) clearTimeout(blinkPulseTimerRef.current);
    };
  }, []);
  // Minimum holds and wake-up clocks persist independently of the current pose.
  const familyRef = useRef<IdleMoodFamily>('calm');
  const heldSinceRef = useRef(0);
  const holdRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sleepSinceRef = useRef<number | null>(null);
  const hiddenAtRef = useRef<number | null>(null);
  const returnPerkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
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
   * holds MIN_EXPRESSION_HOLD_MS before being replaced (anti-zapping).
   * The rig then blends each organ continuously from its current velocity.
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
          frameEmote(next.expression, useEyesSignalsStore.getState().liveReaction(now)),
          emoteGlyphRef,
          emoteTimerRef,
          setEmote
        );
        if (changed) {
          applyAccessory(
            next.expression,
            pendingAccentRef.current,
            accessoryTimerRef,
            setAccessory
          );
          pendingAccentRef.current = 'none';
        }
        deliverOnArrival(
          next.expression,
          now,
          pendingDeliveryRef,
          { beat: accentTimerRef, handOver: handOverTimerRef },
          setAccentBeat
        );
        // Leaving the wandering family cancels the idle life immediately — a
        // directed expression must never carry a stale wander target or
        // gesture. Speaking is directed too: LIA speaks TO the person, so a
        // glance under way when the voice starts comes back to them.
        if (!IDLE_LIFE_EXPRESSIONS.has(next.expression)) {
          setIdleGaze(prev => (prev === null ? prev : null));
          setGesture(prev => (prev === null ? prev : null));
        }
      };
      land();
    },
    [setAccentBeat]
  );

  const evaluate = useCallback(() => {
    const now = Date.now();
    const signals = useEyesSignalsStore.getState();
    const live = readCompanionSignals(now);
    const errorExpired =
      erroredAtRef.current !== null && now - erroredAtRef.current >= ERROR_HOLD_MS;
    const next = sleepPolicyFrame(
      deriveExpression({
        chatStatus: chatStatus === 'error' && errorExpired ? 'idle' : chatStatus,
        streamPhase,
        ...live,
        hitlAwaiting,
        inactivityStage: inactivityStageFor(now - (lastActivityRef.current ?? now)),
      }),
      allowSleep
    );
    // Mood family: the personality channel (breathing pace, blink cadence,
    // gesture weights) — tracked as state for CSS and a ref for the timers.
    const nextFamily = resolveIdleFamily(live.moodLabel, next.expression);
    familyRef.current = nextFamily;
    setFamily(prev => (prev === nextFamily ? prev : nextFamily));
    // How forcefully the last answer was written. It rides alongside the mood
    // family — same shape, same guard against re-rendering on an unchanged
    // value — and scales the pose without ever choosing it.
    const nextEmphasis = signals.liveEmphasis(now);
    setResponseWeight(
      signals.liveReaction(now) === next.expression ? signals.liveReactionWeight(now) : 1
    );
    setEmphasis(prev => (prev === nextEmphasis ? prev : nextEmphasis));
    // The accent fires ONCE per REACTION — keyed on the reaction's own
    // timestamp, not on the accent value. Keyed on the value, two consecutive
    // answers that both earned a wink inside the same hold window would play
    // it once: the second edge never happens because the value never changed.
    const reactionAt = signals.reaction?.at ?? null;
    if (reactionAt !== lastReactionAtRef.current) {
      lastReactionAtRef.current = reactionAt;
      // The movement plays now; the accessory is PARKED for the frame that is
      // about to land, because that is where the accessory has its single
      // owner. Playing it here instead put two writers a few milliseconds
      // apart, and the arrival's roll won.
      const received = receiveAnswer(signals, now, handOverTimerRef);
      pendingAccentRef.current = received.accent;
      pendingDeliveryRef.current = received.delivery;
    }
    playExchangeBeats(chatStatus, finishedToolKey(signals.lastActivity), now, {
      status: beatStatusRef,
      markedTool: markedToolRef,
      heldSince: heldSinceRef,
      beatTimer: accentTimerRef,
      setBeat: setAccentBeat,
      pulseBlink,
    });
    trackSleepClock(next.expression, now, sleepSinceRef);
    // Narrative beats on signal EDGES, idle-stage only (an interactive state
    // owns the face): a cross-family mood shift plays its rise/fall beat; a
    // typing signal that expires without a send plays the "you were
    // saying?" wonder.
    const idleStage = chatStatus === 'idle' && !hitlAwaiting && live.voiceState !== 'speaking';
    // An interactive state — or a live notification ping — cuts any playing
    // performance short: the beats are idle storytelling, never allowed to
    // sit on top of a live exchange or to hide the notification glance.
    if (!idleStage || signals.isNotificationLive(now)) cancelPerformance();
    applyFrame(next, now);
  }, [
    chatStatus,
    streamPhase,
    hitlAwaiting,
    allowSleep,
    cancelPerformance,
    applyFrame,
    pulseBlink,
    setAccentBeat,
  ]);
  useEffect(() => {
    evaluateRef.current = evaluate;
  }, [evaluate]);

  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    const onChange = () => {
      if (!query?.matches) return;
      cancelPerformance();
      cancelHandOver(handOverTimerRef);
      setGesture(null);
      setAccentBeat(null);
      setIdleGaze(null);
      setBlinking(false);
      setWinking(false);
    };
    query?.addEventListener('change', onChange);
    return () => query?.removeEventListener('change', onChange);
  }, [cancelPerformance, setAccentBeat]);

  // Re-derive on every input change: props (via evaluate identity), the live
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
      useLiveStore.subscribe(evaluate),
      useCompanionEnvironmentStore.subscribe(evaluate),
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
    if (!enabled || motionReduced) return;
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
  }, [enabled, motionReduced, pulseBlink]);

  // Idle life: the random gesture loop that keeps the eyes alive between
  // events — gaze wander (saccades/glances with hold-and-return) and one-shot
  // gestures, weighted by the current mood family. Same pending-timer
  // discipline as the blink chain.
  useEffect(() => {
    if (!enabled || motionReduced) return;
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
        setIdleGaze({
          gaze: target,
          ms: kind === 'saccade' ? SACCADE_MOVE_MS : GLANCE_MOVE_MS,
        });
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
        const signals = useEyesSignalsStore.getState();
        const busy = faceIsTaken(signals, Date.now(), accentBeatRef.current);
        // 'speaking' has no wandering life: the gaze holds on the person spoken to.
        const alive =
          !document.hidden &&
          !busy &&
          !winkingRef.current &&
          current.gaze === null &&
          // A face that looks AT something neither wanders nor fidgets: the
          // answer being written has it.
          !current.target &&
          IDLE_LIFE_EXPRESSIONS.has(current.expression);
        if (alive) {
          // The mood is the personality channel of the idle life (soft
          // resting poses carry none) — read fresh at each tick.
          const psyche = usePsycheStore.getState();
          const family = resolveIdleFamily(
            psyche.enabled ? psyche.moodLabel : null,
            current.expression
          );
          const picked = pickIdleGesture(Math.random, family);
          if (picked === 'saccade' || picked === 'glance') {
            playGazeWander(picked);
          } else if (picked !== 'flicker') {
            // Whole-face scenes belong to the rig; a flicker leaves this tick quiet.
            setGesture(picked);
            after(GESTURE_DURATION_MS[picked], () => setGesture(null));
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
  }, [enabled, motionReduced, pulseBlink]);

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
    const timerRefs = [
      winkTimerRef,
      emoteTimerRef,
      accessoryTimerRef,
      accentTimerRef,
      handOverTimerRef,
    ];
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
    blinkMask: false,
    family,
    // An accent outranks the idle gesture: it belongs to the answer that just
    // landed, and the idle life is what happens when nothing has.
    gesture: accentBeat ?? gesture,
    idleGaze,
    emote,
    accessory,
    emphasis,
    responseWeight,
    wink,
  };
}

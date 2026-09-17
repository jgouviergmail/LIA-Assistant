'use client';

/**
 * useEyesRig — the only bridge between React and the animation rig.
 *
 * React declares WHAT the character is doing (an expression, a gaze, a blink,
 * a gesture); the rig decides HOW it gets there, frame by frame, and writes
 * the result straight onto the DOM node as `--rig-*` custom properties. No
 * component state is involved in the motion: a running animation must never
 * re-render a React tree sixty times a second.
 *
 * The loop stops itself. `rig.step()` reports whether anything is still
 * moving, and a settled rig leaves the shared frame clock instead of burning
 * a frame for a face that is not moving — which matters for a widget that
 * sits on screen for the whole session. Every mutation wakes it back up.
 */

import { useEffect, useRef } from 'react';

import {
  blinkTapes,
  GESTURE_SCALE_MIN,
  GESTURE_SCALE_SPAN,
  maskBlinkTapes,
  scaleGestureTapes,
  tapesForGesture,
} from '@/components/eyes/rig/gestures';
import { flipTapes, warpTapes } from '@/components/eyes/rig/choreo';
import { createLifeRandom } from '@/components/eyes/rig/life';
import { createSketchClock } from '@/components/eyes/rig/sketches';
import { createRigWriter } from '@/components/eyes/rig/apply';
import {
  releaseFrames,
  requestFrames,
  type FrameSubscriber,
} from '@/components/eyes/rig/scheduler';
import { createEyeRig, type EyeRig } from '@/components/eyes/rig/runtime';
import { DEFAULT_EYE_STYLE, type EyeStyleId } from '@/components/eyes/eye-styles';
import { prefersReducedMotion } from '@/lib/utils/motion';
import type { SpringConfig } from '@/components/eyes/rig/spring';
import type {
  EyeExpression,
  Gaze,
  IdleGesture,
  IdleMoodFamily,
} from '@/components/eyes/expression-engine';

/** Settling time (99 %) of a critically damped spring, in seconds. */
const CRITICAL_SETTLE_FACTOR = 1.057;

/** Mount counter salting the life seed — module-level on purpose, it is a
 * counter and not state. */
let lifeSalt = 0;

/**
 * The face ANSWERS an eye beat: after a share of the idle gestures, the rig
 * is cued to play its next mimic within a beat, so a glance is followed by a
 * smile in one thought — where two independent timers gave two characters.
 */
export const GESTURE_ANSWER_PROBABILITY = 0.3;
export const GESTURE_ANSWER_MIN_MS = 350;
export const GESTURE_ANSWER_SPAN_MS = 450;

/**
 * ONE sketch clock for the document — module-level on purpose, like the
 * salt: it is the wait itself, and it must outlive the widget. Every page
 * navigation unmounts the eyes; a clock kept in the hook would start the
 * wait over at each one, which is how a character that plays a scene every
 * minute or two came to be seen playing none (measured, 2026-09-17). Handed
 * to every LIVING face; a preview has no life and gets none.
 */
const sketchClock = createSketchClock();

/** A gaze travel time expressed as a spring: a saccade JUMPS (high frequency),
 * an eased return glides. Damping stays just under 1 — an eye landing on a
 * target does not visibly bounce off it. */
function gazeSpringFor(travelMs: number | undefined): SpringConfig | undefined {
  if (travelMs === undefined || travelMs <= 0) return undefined;
  return { frequency: CRITICAL_SETTLE_FACTOR / (travelMs / 1000), damping: 0.95 };
}

export interface UseEyesRigOptions {
  expression: EyeExpression;
  styleId?: EyeStyleId;
  family?: IdleMoodFamily;
  gaze: Gaze | null;
  /** Travel time hint from the host (saccade jump vs eased return). */
  gazeDurationMs?: number;
  /** One blink cycle is running — the rising edge plays it. */
  blinking?: boolean;
  /** The blink masks a face swap: the rig holds the lids shut past it. */
  blinkMask?: boolean;
  /** Active idle gesture — a new one plays its beats. */
  gesture?: IdleGesture | null;
  /** How forcefully the pose should land (1 = as authored). */
  emphasis?: number;
  /**
   * Whether the face lives on its own — mimics and sketches drawn from a
   * private entropy stream, gestures at a drawn size. On by default; the
   * style picker's previews turn it off, because a preview is there to
   * compare silhouettes and a sneeze mid-comparison is not a comparison.
   * The breath and the moving hold stay: they are the pose, not a beat.
   */
  life?: boolean;
}

/**
 * Drive the rig from declarative props.
 *
 * Returns the ref to attach to the eyes root: it is the element the rig
 * writes its channels onto.
 */
export function useEyesRig(options: UseEyesRigOptions) {
  const {
    expression,
    styleId = DEFAULT_EYE_STYLE,
    family = 'calm',
    gaze,
    gazeDurationMs,
    blinking = false,
    blinkMask = false,
    gesture = null,
    emphasis = 1,
    life = true,
  } = options;

  const elementRef = useRef<HTMLSpanElement | null>(null);
  const rigRef = useRef<EyeRig | null>(null);
  const lifeRandomRef = useRef<(() => number) | null>(null);
  const wakeRef = useRef<(() => void) | null>(null);
  // Props the loop must read without re-creating itself.
  const initialRef = useRef({ pose: { expression, styleId, family }, life });

  // --- The loop. Declared first so every sync effect below finds a live rig.
  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;

    // The life's own stream, seeded once per mount (a salt keeps twelve
    // previews mounted in the same millisecond from miming in unison). It
    // never touches `Math.random`: the widget tests pin that one with exact
    // once-sequences, and a draw at construction would shift them all.
    lifeRandomRef.current = initialRef.current.life
      ? createLifeRandom(Date.now() + lifeSalt++ * 7919)
      : null;
    const rig = createEyeRig({
      initial: initialRef.current.pose,
      reducedMotion: prefersReducedMotion(),
      // The one caller that hands the rig real entropy: two angers must never
      // land at exactly the same speed. Tests build rigs without it and stay
      // perfectly deterministic.
      random: Math.random,
      lifeRandom: lifeRandomRef.current ?? undefined,
      sketchClock: lifeRandomRef.current ? sketchClock : undefined,
    });
    const writer = createRigWriter(element);
    rigRef.current = rig;
    writer.write(rig.values());

    // One shared clock for every rig on the page (see `rig/scheduler.ts`):
    // the widget and the twelve style previews step from a single frame.
    const step: FrameSubscriber = delta => {
      const awake = rig.step(delta);
      writer.write(rig.values());
      if (!awake) return 'stop';
      return rig.isSettling() ? 'active' : 'idle';
    };
    const wake = () => requestFrames(step);
    wakeRef.current = wake;
    wake();

    const media =
      typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-reduced-motion: reduce)')
        : null;
    const onMotionPreference = (event: MediaQueryListEvent) => {
      rig.setReducedMotion(event.matches);
      wake();
    };
    media?.addEventListener('change', onMotionPreference);

    return () => {
      media?.removeEventListener('change', onMotionPreference);
      releaseFrames(step);
      wakeRef.current = null;
      rigRef.current = null;
    };
  }, []);

  // --- Pose: expression, style and mood family.
  useEffect(() => {
    rigRef.current?.setPose({ expression, styleId, family, emphasis });
    wakeRef.current?.();
  }, [expression, styleId, family, emphasis]);

  // --- Gaze aim, with the host's travel-time intent turned into physics.
  // Depends on the COORDINATES, never on the object: the host rebuilds its
  // props on every render, and a new identity for the same aim would re-arm
  // the gaze (and wake the loop) sixty times for nothing.
  const gazeX = gaze ? gaze.x : null;
  const gazeY = gaze ? gaze.y : null;
  useEffect(() => {
    const aim = gazeX === null || gazeY === null ? null : { x: gazeX, y: gazeY };
    rigRef.current?.setGaze(aim, gazeSpringFor(gazeDurationMs));
    wakeRef.current?.();
  }, [gazeX, gazeY, gazeDurationMs]);

  // --- Blink: the RISING edge plays one cycle — the mask blink when the
  // host is swapping the face under it, the spontaneous one otherwise. The
  // host holds the flag for the whole cycle, so reacting to the value
  // rather than the edge would replay the tape on every unrelated
  // re-render; the mask is read at the edge and never re-armed by itself.
  const wasBlinkingRef = useRef(false);
  const wasMaskRef = useRef(false);
  useEffect(() => {
    const rising = blinking && !wasBlinkingRef.current;
    // A mask arriving in the middle of a spontaneous blink is an edge of its
    // own: the lids must be held shut again, or the swap lands as they open.
    const maskRising = blinking && blinkMask && !wasMaskRef.current;
    wasBlinkingRef.current = blinking;
    wasMaskRef.current = blinking && blinkMask;
    if (!rising && !maskRising) return;
    rigRef.current?.play(...(blinkMask ? maskBlinkTapes() : blinkTapes()));
    wakeRef.current?.();
  }, [blinking, blinkMask]);

  // --- Gestures: each new one plays its beats once — at a size drawn for
  // the occasion, on a side drawn for it, WARPED in pace and per channel,
  // and answered by the face a share of the time. The same beat twice at
  // the same size on the same brow is a mechanism, and this hook is the one
  // caller that carries entropy (the rig itself stays pure).
  useEffect(() => {
    if (!gesture) return;
    const tapes = tapesForGesture(gesture);
    if (tapes.length === 0) return;
    const draw = lifeRandomRef.current;
    const rig = rigRef.current;
    if (!draw) {
      rig?.play(...tapes);
      wakeRef.current?.();
      return;
    }
    const scaled = scaleGestureTapes(tapes, GESTURE_SCALE_MIN + draw() * GESTURE_SCALE_SPAN);
    const sided = draw() < 0.5 ? flipTapes(scaled) : scaled;
    rig?.play(...warpTapes(sided, draw));
    if (draw() < GESTURE_ANSWER_PROBABILITY) {
      rig?.answerIn(GESTURE_ANSWER_MIN_MS + draw() * GESTURE_ANSWER_SPAN_MS);
    }
    wakeRef.current?.();
  }, [gesture]);

  return elementRef;
}

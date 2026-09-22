/**
 * The rig runtime — one integrator, no DOM.
 *
 * Every frame it resolves, for each channel:
 *
 *     target   = active tape  >  gaze aim  >  expression pose
 *     value    = spring(target)  +  loops
 *
 * Springs give the arrival its physics (and keep the velocity across an
 * interruption); tapes give it its beats (anticipation, blink, one-shots);
 * loops give it the motion that never arrives (breath, shiver, scan). The
 * three compose by construction, which is the whole reason the CSS keyframes
 * they replace could not: a keyframe REPLACES the property it animates, so a
 * loop and a pose could never share a transform.
 *
 * Purity is deliberate — the clock is an argument, so a test drives the rig
 * frame by frame and asserts what the eyes actually DO, which no test of the
 * previous system could.
 */

import {
  CHANNELS,
  CHANNEL_KEYS,
  isDerived,
  restChannelValues,
  type ChannelKey,
  type ChannelValues,
} from '@/components/eyes/rig/channels';
import {
  DYNAMICS,
  DYNAMICS_FOR_EXPRESSION,
  FAMILY_DYNAMICS,
  leadMsFor,
  type Dynamics,
  type DynamicsName,
} from '@/components/eyes/rig/dynamics';
import {
  contextualPose,
  NEUTRAL_CONTEXT,
  thoughtPattern,
  activityPattern,
  type ActingContext,
} from './direction';
import { loopValue, type LoopSpec } from '@/components/eyes/rig/loops';
import { exaggeratePose, resolveLoops, resolvePose } from '@/components/eyes/rig/poses';
import { ambientMotion } from './ambient';
import {
  isSpringAtRest,
  REST_EPSILON,
  springStep,
  type SpringConfig,
  type SpringState,
} from '@/components/eyes/rig/spring';
import {
  anticipationTape,
  tapeDurationMs,
  tapeTargetAt,
  type Tape,
} from '@/components/eyes/rig/tape';
import { ARRIVAL_SCRIPTS, resolvePatterns } from '@/components/eyes/rig/scripts';
import {
  createLifeRandom,
  drawMouthLifeDelayMs,
  drawMouthMimic,
  MOUTH_LIFE_EXPRESSIONS,
  type MouthMimic,
} from '@/components/eyes/rig/life';
import { warpTapes } from '@/components/eyes/rig/choreo';
import {
  armSketchClock,
  createSketchClock,
  pickSketch,
  recordSketch,
  SKETCH_EXPRESSIONS,
  SKETCH_MOUTH_GRACE_MS,
  sketchDurationMs,
  sketchTapes,
  type SketchClock,
} from '@/components/eyes/rig/sketches';
import { DEFAULT_EYE_STYLE, type EyeStyleId } from '@/components/eyes/eye-styles';
import { clampGazeAxis } from '@/components/eyes/expression-engine';
import type { EyeExpression, Gaze, IdleMoodFamily } from '@/components/eyes/expression-engine';

/** What the host tells the rig about the character's current state. */
const CONTOUR_SPRING = { frequency: 1.2, damping: 1 };
const HEAD_SPRING = { frequency: 1.35, damping: 1 };
const AMBIENT_SPRING = { frequency: 0.85, damping: 1 };

export interface RigPose {
  readonly expression: EyeExpression;
  readonly styleId: EyeStyleId;
  readonly family: IdleMoodFamily;
  /**
   * How forcefully the pose should land, from how the answer was written
   * (1 = as authored). It scales the SAME expression up or down; it never
   * picks a different one, and it never comes from the psyche.
   */
  readonly emphasis?: number;
  readonly responseWeight?: number;
}

/** Anticipation settings. Ratio and lead are the animator's dial; `minDelta`
 * keeps a twitch from being dressed up as intent. */
const ANTICIPATION = {
  ratio: 0.16,
  leadMs: 95,
  minDelta: 0.09,
  maxOffset: 0.22,
} as const;

/** Anticipation applies to the WILLED motion of the face — its pose, its
 * brows and its mass. Lids and radii follow the move; anticipating them too
 * reads as a stutter rather than as intent. */
const ANTICIPATED_GROUPS: ReadonlySet<string> = new Set(['pose', 'brow', 'mass']);

/** Rotations travel in degrees, so they need their own, wider, thresholds. */
const ANTICIPATION_DEG = {
  ratio: 0.16,
  leadMs: 95,
  minDelta: 2.5,
  maxOffset: 4,
} as const;

/**
 * Arc gain — an eye does not travel in a straight line.
 *
 * The vertical bias is proportional to the HORIZONTAL speed, so it is zero at
 * both ends of the move and greatest in the middle: that is an arc, and it is
 * the fourth animation principle. It rides the OUTPUT, never the springs, so
 * it perturbs nothing and vanishes the moment the gaze settles.
 */
const ARC_GAIN = 0.07;
const ARC_MAX = 0.35;

/**
 * Velocity squash and stretch, at constant volume: the pair stretches along
 * its direction of travel and thins across it.
 *
 * The gain is calibrated, not guessed: measured in a browser (2026-08-31), a
 * full-width saccade peaks at ~0.7 em/s of screen travel, so 0.02 produced a
 * 1.6 % deformation — present in the numbers and invisible to a viewer. At
 * 0.08 the same saccade peaks near 6 %, which reads as weight without tipping
 * into caricature; the cap keeps a pathological velocity from stretching the
 * eyes into ribbons.
 *
 * Below the threshold the direction means nothing, so the angle is HELD rather
 * than recomputed from noise — an angle jittering at rest would rewrite the
 * style attribute on every frame of a settled face.
 */
const STRETCH_GAIN = 0.08;
const STRETCH_MAX = 0.14;
const STRETCH_EPSILON = 0.005;

/** Visual travel per unit of gaze, matching the stylesheet own factors: the
 * deformation must follow the direction the eyes actually MOVE on screen,
 * not the direction in the abstract gaze space. */
const GAZE_EM_PER_UNIT_X = 0.09;
const GAZE_EM_PER_UNIT_Y = 0.07;

/**
 * Secondary couplings — what the brows do BECAUSE of the rest of the face.
 *
 * Looking up lifts the brows and looking down relaxes them (the eye and the
 * brow share a muscle sheet, and every animator draws it), and a blink drags
 * each brow down with ITS lid, so the reopening rebound lifts it back. Both
 * are contributions on the OUTPUT, like the arc: they perturb no spring, need
 * no channel, and vanish the moment their cause does.
 *
 * They live here and not in the stylesheet on purpose. A coupling is motion,
 * and the boundary rule gives motion to the rig; written as a `calc()` it
 * would be a constant nothing can read, invisible to every frame test and to
 * the bubble guard that has to know how high a brow can reach.
 */
export const BROW_GAZE_LIFT_EM = 0.03;
export const BROW_BLINK_DIP_EM = 0.03;
/** A smile pushes the cheeks up and the brows with them, a hair, per unit of
 * curve above the resting one. One-sided: a frown pushes nothing. */
export const BROW_SMILE_LIFT_EM = 0.02;

/**
 * Squash and stretch of the BROW, derived from its own motion.
 *
 * A brow that shoots up thins into a long arc; one pressed down thickens and
 * shortens — the weight of the organ, which a bar of constant thickness
 * never had. Derived rather than declared (like the velocity stretch of the
 * pair): no pose has to remember it, no beat can forget it, and it is one
 * implementation the bubble guard reads too. Per em of raise (negative Y is
 * up) and per unit of arch above the resting one, bounded so the sheet is
 * never asked for a hair or a slab.
 */
export const BROW_STRETCH_PER_EM = 2.2;
export const BROW_STRETCH_PER_ARC = 0.2;
export const BROW_STRETCH_MIN = 0.6;
export const BROW_STRETCH_MAX = 1.4;

export function browStretchFor(browY: number, browArc: number): number {
  const stretch =
    1 + browY * BROW_STRETCH_PER_EM - (browArc - CHANNELS.browArcL.rest) * BROW_STRETCH_PER_ARC;
  return Math.min(BROW_STRETCH_MAX, Math.max(BROW_STRETCH_MIN, stretch));
}

/** The narrowest a mouth is drawn, as a fraction of the style span. */
export const MOUTH_WIDTH_FLOOR = 0.2;

/**
 * How long the pose's pull BUILDS UP when a beat hands a channel back.
 *
 * A tape ends and the channel goes home on the pose's dynamics: the
 * position and the velocity carry across, but the TARGET jumps at that
 * instant (from the held shape back to the pose) and the acceleration
 * jumps with it — the whole pull of the pose in one frame, which the eye
 * reads as a kink at the top of the motion. So the pull takes hold
 * progressively: the spring's frequency ramps from a fraction of the
 * pose's to the whole over this window, the acceleration starts near zero
 * and grows, continuous by construction. Only a hand-over FROM a beat
 * blends. A beat's own attack is never softened (its spring is the
 * author's), a hold letting go onto a release keeps the release's own
 * spring (the author chose it), and a new EXPRESSION changes the pose
 * dynamics outright — a startle blended out of a sad face would be a
 * startle dulled by the face it interrupts.
 */
export const SPRING_BLEND_MS = 120;
/** Where the ramp starts, as a fraction of the pose's frequency — above
 * zero, because a spring at zero frequency snaps instead of pulling. */
const SPRING_BLEND_FROM = 0.1;

interface SpringBlend {
  /** The spring in force, and whether a beat imposed it. */
  spring: SpringConfig;
  fromBeat: boolean;
  /** The spring being blended out of, while a blend is on. */
  blendFrom: SpringConfig | null;
  blendAtMs: number;
}

function lerp(from: number, to: number, t: number): number {
  return from + (to - from) * t;
}

/**
 * The flattest an eye is drawn by a BEAT. A grin squashes the eyes into
 * happy arcs; on a pose that is already a dome (joy squashes to 0.55) the
 * same offset would close them past a sliver. A tenth is the closed happy
 * eye of the cartoons, and it stays under the deepest folded lid a squash
 * style draws (a `sleep` on `anneaux` flattens to 0.14), so no pose is
 * ever clipped by it.
 */
export const EYE_SQUASH_FLOOR = 0.1;

interface ActiveTape {
  readonly tape: Tape;
  elapsedMs: number;
}

export interface EyeRig {
  /** Land a new expression (or restyle the current one). */
  setPose(pose: RigPose): void;
  setContext(context: ActingContext): void;
  /** Aim the gaze, or hand it back to centre with `null`. The optional
   * spring carries the host's travel intent: a saccade JUMPS, a return
   * glides. Omitted, the expression's own gaze dynamics apply. */
  setGaze(gaze: Gaze | null, spring?: SpringConfig): void;
  /** Play one or more one-shot beats. Ignored under reduced motion. */
  play(...tapes: readonly Tape[]): void;
  /**
   * Play a SKETCH — a whole scene of tapes (`rig/sketches.ts`). Replaces any
   * sketch in progress, stands the face's own life aside for its duration,
   * and is dropped by the next expression change. Ignored under reduced
   * motion. The rig draws its own sketches from `lifeRandom`; this is the
   * door for the host, the harness and the tests.
   */
  playSketch(tapes: readonly Tape[]): void;
  /** True while a sketch is on. */
  isPerforming(): boolean;
  /**
   * Cue the face to ANSWER within `delayMs` — the host calls it after an
   * eye beat, for a share of them, so a glance is followed by a smile in
   * one thought rather than two timers. Brings the next mimic forward and
   * never queues one: on a face that is not resting, the cue is dropped.
   */
  answerIn(delayMs: number): void;
  /** The clock the sketches run on — the host's if it handed one, else the
   * rig's own. Read it, never replace it. */
  sketchClock(): Readonly<SketchClock>;
  /** Advance the simulation. Returns whether anything is still moving. */
  step(dtMs: number): boolean;
  /** Live view of the current channel values — read it, never retain it. */
  values(): Readonly<ChannelValues>;
  /** True while a spring, a tape or a loop still has something to do. */
  isAwake(): boolean;
  /** True while something is genuinely TRAVELLING — a spring still on its
   * way, or a beat playing. False when the only motion left is the
   * perpetual breathing and drift, which need far fewer frames. */
  isSettling(): boolean;
  /** Snap every channel onto its target (reduced motion, first paint). */
  settle(): void;
  setReducedMotion(reduced: boolean): void;
}

export interface RigOptions {
  /** Start the rig already settled on this pose (avoids a boot animation). */
  readonly initial?: RigPose;
  readonly reducedMotion?: boolean;
  /**
   * Entropy for arrival TIMING — two angers are never quite the same speed.
   *
   * Without it a face lands every emotion on the identical curve, and
   * identical repetition is the most reliable way to read as a machine.
   * Omitted, the rig is perfectly deterministic (which is what every test
   * wants); the React binding is the one caller that passes a real source.
   */
  readonly random?: () => number;
  /**
   * Entropy for the mouth's OWN life (`rig/life.ts`): which mimic, when,
   * which side, what size. A separate stream from `random` on purpose — the
   * host seeds it once per mount, so a life that draws at construction can
   * never shift the pinned `Math.random` sequences the widget tests read.
   * Omitted, the mouth has no life of its own and the rig stays exactly as
   * still as its loops make it.
   */
  readonly lifeRandom?: () => number;
  /**
   * The clock the sketches wait on (`rig/sketches.ts`), kept by the host
   * across mounts so a page navigation never restarts the wait. It counts
   * RESTING time only, and the rig mutates it in place. Omitted, the rig
   * keeps a private one.
   */
  readonly sketchClock?: SketchClock;
}

/** How much an arrival's pace may vary, either way. Small on purpose: this
 * is the difference between a repetition and a performance, not a wobble. */
const ARRIVAL_JITTER = 0.16;

const DEFAULT_POSE: RigPose = {
  expression: 'neutral',
  styleId: DEFAULT_EYE_STYLE,
  family: 'calm',
};

/** The seed a rig without entropy generates its patterns from. */
const PATTERN_SEED = 0x51de;

export function createEyeRig(options: RigOptions = {}): EyeRig {
  const pose: RigPose = { ...DEFAULT_POSE, ...options.initial };
  const random = options.random;
  const lifeRandom = options.lifeRandom;
  let context: ActingContext = { ...NEUTRAL_CONTEXT };
  /** What the state's PATTERNS are generated from — the life stream when the
   * rig has one, else a seeded stream of the rig's own, so a rig built
   * without entropy still speaks, and always the same way. */
  const patternRandom = lifeRandom ?? createLifeRandom(PATTERN_SEED);
  let reducedMotion = options.reducedMotion ?? false;
  let arrivalPace = 1;
  let responseWeight = pose.responseWeight ?? 1;

  /** The pose an expression lands on, exaggerated by the mood family AND
   * by how emphatically the answer that caused it was written. */
  function computeTargets(
    nextExpression: EyeExpression,
    nextStyle: EyeStyleId,
    nextFamily: IdleMoodFamily,
    nextEmphasis: number
  ): ChannelValues {
    const target = exaggeratePose(
      resolvePose('neutral', nextStyle),
      resolvePose(nextExpression, nextStyle),
      FAMILY_DYNAMICS[nextFamily].amplitude * nextEmphasis
    );
    if (responseWeight < 1) {
      const rest = resolvePose('neutral', nextStyle);
      for (const key of CHANNEL_KEYS)
        target[key] = rest[key] + (target[key] - rest[key]) * Math.max(0, responseWeight);
    }
    return contextualPose(target, nextExpression, context);
  }

  let emphasis = pose.emphasis ?? 1;
  let poseTargets: ChannelValues = computeTargets(
    pose.expression,
    pose.styleId,
    pose.family,
    emphasis
  );
  let loops: LoopSpec[] = resolveLoops(pose.expression, pose.family);
  let activeDynamics: Dynamics = scaleDynamics(
    DYNAMICS_FOR_EXPRESSION[pose.expression],
    pose.family
  );
  let expression: EyeExpression = pose.expression;
  let styleId: EyeStyleId = pose.styleId;
  let family: IdleMoodFamily = pose.family;
  let gaze: Gaze | null = null;
  let gazeSpring: SpringConfig | undefined;

  const springs: Record<ChannelKey, SpringState> = {} as Record<ChannelKey, SpringState>;
  const output: ChannelValues = restChannelValues();
  for (const key of CHANNEL_KEYS) {
    springs[key] = { value: poseTargets[key], velocity: 0 };
    output[key] = poseTargets[key];
  }

  // Indexed at construction too: a rig created on a breathing expression must
  // breathe from its first frame, not from its first pose change.
  let loopsByChannel = indexLoops(loops);
  let tapes: ActiveTape[] = [];
  /** Looping behaviour owned by the current expression (the search
   * saccades). Re-resolved on every pose change, so a pattern can never
   * outlive the state that asked for it. */
  let patterns: ActiveTape[] = startPatterns(pose.expression);
  /** The sketch in progress — one scene of tapes, outranked by one-shot
   * beats and outranking the state's patterns. Dropped on any expression
   * change. */
  let sketch: ActiveTape[] = [];
  /** When the current sketch ends on the rig clock (0 when none). */
  let sketchUntilMs = 0;
  let clockMs = 0;

  /** Last stretch axis, held while the eyes are too slow for it to mean
   * anything (see STRETCH_EPSILON). */
  let stretchAngle = 0;

  /** Whether something was still travelling at the last step. `isSettling` is
   * asked once per frame by the scheduler, immediately after `step`, and
   * recomputing it there would walk all fifty channels a second time for an
   * answer just produced. Every mutation that starts motion sets it directly,
   * so it can never be read stale. */
  let lastSettling = true;

  /** Per channel, the spring in force and the blend out of the previous one
   * (see `SPRING_BLEND_MS`). Filled lazily: a channel that never moves
   * never gets an entry. */
  const springBlends: Partial<Record<ChannelKey, SpringBlend>> = {};

  /**
   * When the mouth's own life next plays a mimic, on the rig clock — only
   * ever set when the rig has an entropy source (see `rig/life.ts`). A rig
   * without one is exactly as still as it was, which is what every test
   * wants, and what the pixel budget of the moving hold is measured on.
   */
  let mouthLifeAtMs = lifeRandom ? drawMouthLifeDelayMs(lifeRandom) : Number.POSITIVE_INFINITY;
  /** The last mimic played — never drawn twice in a row — and when its
   * longest tape ends: an answer cued while it plays would stack a second
   * face on the first. */
  let lastMimic: MouthMimic | null = null;
  let mouthBusyUntilMs = 0;
  /** The sketch clock — armed here only when the host hands a fresh one (or
   * none): a clock that already waits keeps waiting, which is the point of
   * handing it over. Drawn AFTER the mouth life, as the tests' sequences
   * expect. */
  const sketchClock = options.sketchClock ?? createSketchClock();
  if (lifeRandom && sketchClock.dueMs <= 0) armSketchClock(sketchClock, lifeRandom);

  /** Play the next mimic if its time has come; reschedule either way. Runs
   * on BOTH step paths: a resting face is on the idle path by definition.
   * A sketch in progress holds it: two things acting on one face at once
   * read as two characters. */
  function tickMouthLife(): void {
    if (!lifeRandom || reducedMotion || clockMs < mouthLifeAtMs) return;
    if (context.activity || context.responding || clockMs < sketchUntilMs) return;
    mouthLifeAtMs = clockMs + drawMouthLifeDelayMs(lifeRandom);
    if (!MOUTH_LIFE_EXPRESSIONS.has(expression)) return;
    const draw = drawMouthMimic(lifeRandom, lastMimic, context);
    lastMimic = draw.mimic;
    mouthBusyUntilMs = clockMs + Math.max(...draw.tapes.map(tapeDurationMs));
    for (const tape of draw.tapes) tapes.push({ tape, elapsedMs: 0 });
    lastSettling = true;
  }

  /** Start a scene: the tapes, the curtain time, and the face's own life
   * stood aside until a breath after the end. */
  function playSketch(list: readonly Tape[]): void {
    if (reducedMotion || context.activity || context.responding || list.length === 0) return;
    tapes = tapes.filter(active => CHANNELS[active.tape.channel].group === 'blink');
    sketch = list.map(tape => ({ tape, elapsedMs: 0 }));
    sketchUntilMs = clockMs + sketchDurationMs(list);
    mouthLifeAtMs = Math.max(mouthLifeAtMs, sketchUntilMs + SKETCH_MOUTH_GRACE_MS);
    lastSettling = true;
  }

  /**
   * Advance the sketch clock by this frame's RESTING time and play the next
   * scene when it is due — only on a resting face, never over a scene
   * already on. A frame spent on a thought, a reply or a reaction counts
   * for nothing, so a scene is never lost to one: it waits.
   */
  function tickSketchLife(dtMs: number): void {
    if (!lifeRandom || reducedMotion) return;
    if (
      context.activity ||
      context.responding ||
      !SKETCH_EXPRESSIONS.has(expression) ||
      sketch.length > 0
    )
      return;
    sketchClock.restedMs += dtMs;
    if (sketchClock.restedMs < sketchClock.dueMs) return;
    const name = pickSketch(lifeRandom, sketchClock.recent);
    // Warped: the same scene twice is never the same performance.
    playSketch(warpTapes(sketchTapes(name), lifeRandom));
    recordSketch(sketchClock, name);
    armSketchClock(sketchClock, lifeRandom);
  }

  // Derive the computed channels once, before anyone can read them: the
  // constructor copies POSE targets into the output, and a derived channel
  // has none. Without this the first painted frame carries a resting curve
  // with a zero arc — a one-frame contradiction, on the very frame whose
  // whole point is to be already correct. It must run AFTER every `let` it
  // reads (the loop index, the patterns): a temporal dead zone here throws
  // inside the constructor and takes the entire widget down.
  writeOutput();

  /** The looping behaviour a state runs — none at all under reduced
   * motion. One helper for the three places that start patterns, so the
   * preference cannot be honoured on two of them and forgotten on the
   * third (it was, on the constructor). */
  function startPatterns(next: EyeExpression, elapsedMs = 0): ActiveTape[] {
    if (reducedMotion) return [];
    const pattern =
      context.activity && ['thinking', 'searching', 'focused', 'attentive'].includes(next)
        ? activityPattern(context.activity, patternRandom)
        : next === 'thinking'
          ? thoughtPattern(patternRandom)
          : resolvePatterns(next, patternRandom);
    return pattern.map(tape => ({ tape, elapsedMs }));
  }

  /** Where a channel is heading right now: a playing tape wins, then the gaze
   * aim for the two gaze channels, then the pose. */
  function baseTargetFor(key: ChannelKey): number {
    if (key === 'headYaw') return clampGazeAxis(springs.gazeX.value);
    if (key === 'headPitch') return clampGazeAxis(springs.gazeY.value);
    if (key === 'gazeX' || key === 'hlX') return gaze?.x ?? 0;
    if (key === 'gazeY' || key === 'hlY') return gaze?.y ?? 0;
    return poseTargets[key];
  }

  /** A one-shot beat outranks the state's own looping pattern: a blink
   * still blinks in the middle of a search. */
  function tapeTargetIn(list: ActiveTape[], key: ChannelKey): number | null {
    for (let index = list.length - 1; index >= 0; index -= 1) {
      const active = list[index];
      if (active.tape.channel !== key) continue;
      const value = tapeTargetAt(active.tape, active.elapsedMs);
      if (value === null) continue;
      return active.tape.relative ? baseTargetFor(key) + value : value;
    }
    return null;
  }

  function targetFor(key: ChannelKey): number {
    const beat = tapeTargetIn(tapes, key);
    if (beat !== null) return beat;
    const scene = tapeTargetIn(sketch, key);
    if (scene !== null) return scene;
    const pattern = tapeTargetIn(patterns, key);
    if (pattern !== null) return pattern;
    return baseTargetFor(key);
  }

  /**
   * The expression's springs, already scaled by the mood family.
   *
   * Exaggeration is not only amplitude: a lively character also gets THERE
   * quicker, and a drowsy one drags. Scaling is done ONCE per pose change
   * rather than per channel per frame — the naive version allocated a fresh
   * config object forty-odd times a frame for every non-calm mood, which is
   * garbage generated sixty times a second for a constant.
   */
  function scaleDynamics(name: DynamicsName, nextFamily: IdleMoodFamily): Dynamics {
    const preset = DYNAMICS[name];
    // Emphasis reaches the PACE at half strength: an emphatic answer lands
    // quicker as well as bigger, but doubling both would read as a jitter
    // rather than as insistence.
    const factor = FAMILY_DYNAMICS[nextFamily].frequency * arrivalPace * (1 + (emphasis - 1) * 0.5);
    if (factor === 1) return preset;
    const scaled: Record<string, SpringConfig> = {};
    for (const [group, config] of Object.entries(preset)) {
      scaled[group] = {
        frequency: config.frequency * factor,
        damping: config.damping,
      };
    }
    return scaled as Dynamics;
  }

  /** The spring a playing tape imposes on a channel, or null. Split out
   * of `springFor` rather than iterating `[tapes, patterns]`: that literal
   * allocated an array PER CHANNEL PER FRAME — forty-odd of them sixty
   * times a second, which is the same garbage the dynamics scaling was
   * fixed for. */
  function tapeSpringIn(list: ActiveTape[], key: ChannelKey): SpringConfig | null {
    for (let index = list.length - 1; index >= 0; index -= 1) {
      const active = list[index];
      if (active.tape.channel !== key || !active.tape.spring) continue;
      // A tape whose first key is still ahead has not taken the channel:
      // its spring must not lead either. A release tape starts where the
      // hold ends, on a slow spring — read before its time, that spring
      // slowed the attack it was written to follow (found by a test).
      if (active.elapsedMs < active.tape.keys[0].atMs) continue;
      return active.tape.spring;
    }
    return null;
  }

  /** The spring a channel is driven by right now: a playing beat's own, or
   * the pose's — blended across a hand-over between the two. */
  function springFor(key: ChannelKey): SpringConfig {
    if (key.startsWith('weather') || key.startsWith('light')) return AMBIENT_SPRING;
    if (key === 'headYaw' || key === 'headPitch') return HEAD_SPRING;
    // Even a reflex morphs its drawn contour instead of snapping the topology.
    if (key.startsWith('stroke')) return CONTOUR_SPRING;
    const beatSpring =
      tapeSpringIn(tapes, key) ?? tapeSpringIn(sketch, key) ?? tapeSpringIn(patterns, key);
    const group = CHANNELS[key].group;
    const next =
      beatSpring ?? (gazeSpring && group === 'gaze' ? gazeSpring : activeDynamics[group]);
    return blendedSpring(key, next, beatSpring !== null);
  }

  /** Where a channel's blend stands right now; over, it is the spring. */
  function currentSpring(blend: SpringBlend): SpringConfig {
    if (!blend.blendFrom) return blend.spring;
    const t = (clockMs - blend.blendAtMs) / SPRING_BLEND_MS;
    if (t >= 1) {
      blend.blendFrom = null;
      return blend.spring;
    }
    return {
      frequency: lerp(blend.blendFrom.frequency, blend.spring.frequency, t),
      damping: lerp(blend.blendFrom.damping, blend.spring.damping, t),
    };
  }

  function blendedSpring(key: ChannelKey, next: SpringConfig, fromBeat: boolean): SpringConfig {
    const blend = springBlends[key];
    if (!blend) {
      springBlends[key] = {
        spring: next,
        fromBeat,
        blendFrom: null,
        blendAtMs: clockMs,
      };
      return next;
    }
    if (blend.spring !== next) {
      // A beat handing the channel back: the pose's pull builds up from a
      // fraction of itself. Anything else takes the new spring outright.
      const handedBack = blend.fromBeat && !fromBeat;
      blend.blendFrom = handedBack
        ? {
            frequency: next.frequency * SPRING_BLEND_FROM,
            damping: next.damping,
          }
        : null;
      blend.blendAtMs = clockMs;
      blend.spring = next;
      blend.fromBeat = fromBeat;
    }
    return currentSpring(blend);
  }

  /** Loops indexed by the channel they ride. Scanning the whole list once
   * per channel per frame is forty-odd times the work for the same answer,
   * on a widget that is on screen for the entire session. */
  function indexLoops(list: readonly LoopSpec[]): Map<ChannelKey, LoopSpec[]> {
    const index = new Map<ChannelKey, LoopSpec[]>();
    for (const loop of list) {
      const existing = index.get(loop.channel);
      if (existing) existing.push(loop);
      else index.set(loop.channel, [loop]);
    }
    return index;
  }

  function writeOutput(): void {
    for (const key of CHANNEL_KEYS) {
      if (isDerived(key)) continue;
      output[key] = springs[key].value;
    }
    // Add the loops by walking the LOOPS, not the channels: at any moment a
    // handful of channels are ridden and fifty are not, so asking every
    // channel whether it has a loop is fifty lookups for six answers — sixty
    // times a second, for the whole session.
    if (!reducedMotion) {
      for (const [key, riding] of loopsByChannel) {
        let offset = 0;
        for (const loop of riding) offset += loopValue(loop, clockMs);
        output[key] += offset;
      }
    }

    writeDerived();
  }

  /** What the loops add to one channel right now — zero under reduced
   * motion, where no loop runs at all. */
  function loopOffsetFor(key: ChannelKey): number {
    if (reducedMotion) return 0;
    const riding = loopsByChannel.get(key);
    if (!riding) return 0;
    let offset = 0;
    for (const loop of riding) offset += loopValue(loop, clockMs);
    return offset;
  }

  /**
   * The channels computed FROM the motion rather than sprung. Cheap, and
   * shared by both step paths.
   *
   * Every contribution here is written as an ABSOLUTE value from the spring
   * and the loops, never as `output[key] += …`: the idle path only rewrites
   * the channels a loop rides, so an increment on anything else would be
   * added again on every quiet frame and drift, silently, for the whole
   * session. Pinned by a test that compares twenty thousand small steps
   * against one big one.
   */
  function writeDerived(): void {
    Object.assign(output, ambientMotion(output, clockMs, reducedMotion));
    const vx = springs.gazeX.velocity;
    const vy = springs.gazeY.velocity;

    // Arcs: the vertical bias peaks mid-travel and lifts the eyes, the way an
    // eye rides its socket instead of sliding along a rail.
    output.gazeY -= Math.min(Math.abs(vx) * ARC_GAIN, ARC_MAX);

    // Squash and stretch, from the velocity the springs actually produced.
    const screenVx = vx * GAZE_EM_PER_UNIT_X;
    const screenVy = vy * GAZE_EM_PER_UNIT_Y;
    const stretch = Math.min(Math.hypot(screenVx, screenVy) * STRETCH_GAIN, STRETCH_MAX);
    if (stretch > STRETCH_EPSILON) {
      stretchAngle = (Math.atan2(screenVy, screenVx) * 180) / Math.PI;
    }
    output.stretchK = stretch;
    output.stretchA = stretchAngle;

    // The mouth: ONE signed curve becomes a depth and a direction, because a
    // stylesheet can take neither an absolute value nor a sign. Keeping the
    // pose side signed is what lets a smile and a frown be the same shape —
    // and lets the spring travel continuously between them.
    const curve = output.mouthCurve;
    output.mouthArc = Math.min(1, Math.abs(curve));

    // The opening is bounded to what the mouth can draw: the speech envelope
    // deliberately drives the flap THROUGH the closure to make a pause, and a
    // negative opening would shrink the bar under its own ink.
    output.mouthOpen = Math.min(1, Math.max(0, output.mouthOpen));
    // ...and the width keeps a floor: a pucker scaled up on an already narrow
    // mouth must stay a small mouth, never a dot or a negative span.
    output.mouthW = Math.max(MOUTH_WIDTH_FLOOR, output.mouthW);
    output.syL = Math.max(EYE_SQUASH_FLOOR, output.syL);
    output.syR = Math.max(EYE_SQUASH_FLOOR, output.syR);

    // The brows follow the gaze, their own lid and the smile. Absolute, from
    // the spring (see above): the gaze read here is the OUTPUT gaze, arc
    // included, so a horizontal saccade lifts the brows a hair mid-travel —
    // as it should — and the smile read here is the output curve, so a grin
    // beat lifts them with it.
    const gazeLift = output.gazeY * BROW_GAZE_LIFT_EM;
    const smileLift = Math.max(0, curve - CHANNELS.mouthCurve.rest) * BROW_SMILE_LIFT_EM;
    output.browYL =
      springs.browYL.value +
      loopOffsetFor('browYL') +
      gazeLift -
      smileLift +
      springs.blinkL.value * BROW_BLINK_DIP_EM;
    output.browYR =
      springs.browYR.value +
      loopOffsetFor('browYR') +
      gazeLift -
      smileLift +
      springs.blinkR.value * BROW_BLINK_DIP_EM;
    // ...and their weight follows where they ended up.
    output.browSL = browStretchFor(output.browYL, output.browArcL);
    output.browSR = browStretchFor(output.browYR, output.browArcR);
  }

  /**
   * Pure idle: every spring has arrived, nothing is playing, and the only
   * thing still moving is the perpetual breath and drift.
   *
   * The full step walks fifty-odd channels to integrate springs that are all
   * already on their targets. Here six channels are ridden and the rest are
   * unchanged by definition, so it updates exactly those — the same answer
   * as the idle cadence, one level down, and the one that matters for a
   * widget that is on screen all day.
   */
  function stepIdle(dtMs: number): void {
    clockMs += dtMs;
    for (const [key, riding] of loopsByChannel) {
      let offset = 0;
      for (const loop of riding) offset += loopValue(loop, clockMs);
      output[key] = springs[key].value + offset;
    }
    // Derived channels are recomputed unconditionally: they are a handful of
    // float operations, and skipping them would leave a stale arc the day a
    // loop is put on a channel one of them reads.
    writeDerived();
  }

  /**
   * Advance the timed material: one-shot beats expire, patterns wrap.
   *
   * Patterns do NOT expire — they last exactly as long as the expression that
   * owns them. A pattern that reaches the end of its cycle is RESOLVED AGAIN
   * rather than rewound, carrying the time it ran over: a fixed table (the
   * search) comes back identical, which is a wrap; a generated one (speech)
   * comes back as a new chunk, which is how a long answer never loops.
   */
  function advanceBeats(dtMs: number): void {
    if (tapes.length > 0) {
      for (const active of tapes) active.elapsedMs += dtMs;
      tapes = tapes.filter(active => active.elapsedMs <= tapeDurationMs(active.tape));
    }
    if (sketch.length > 0) {
      for (const active of sketch) active.elapsedMs += dtMs;
      sketch = sketch.filter(active => active.elapsedMs <= tapeDurationMs(active.tape));
      if (sketch.length === 0) {
        sketchUntilMs = 0;
        if (sketchClock.scene) sketchClock.completed += 1;
        sketchClock.scene = null;
      }
    }
    let leftoverMs = -1;
    for (const active of patterns) {
      const cycle = tapeDurationMs(active.tape);
      if (cycle <= 0) continue;
      active.elapsedMs += dtMs;
      if (active.elapsedMs >= cycle) leftoverMs = Math.max(leftoverMs, active.elapsedMs - cycle);
    }
    if (leftoverMs >= 0) patterns = startPatterns(expression, leftoverMs);
  }

  /**
   * Integrate every sprung channel one frame towards its current target.
   *
   * Two skips carry the cost of this loop. A channel sitting exactly on its
   * target with no velocity has nothing to integrate — during a quiet minute
   * that is nearly every channel, and each one skipped is a handful of
   * transcendental calls the loop does not make sixty times a second for a
   * face that is only breathing. And snapping onto the target once the spring
   * is within tolerance is what makes that skip reachable at all: an asymptote
   * never arrives on its own.
   */
  function integrateSprings(dtMs: number): void {
    for (const key of CHANNEL_KEYS) {
      if (isDerived(key)) continue;
      const target = targetFor(key);
      if (reducedMotion || CHANNELS[key].snap) {
        springs[key] = { value: target, velocity: 0 };
        continue;
      }
      const state = springs[key];
      if (state.velocity === 0 && state.value === target) continue;
      const next = springStep(state, target, springFor(key), dtMs);
      springs[key] = isSpringAtRest(next, target) ? { value: target, velocity: 0 } : next;
    }
  }

  function interruptPerformance(): void {
    tapes = tapes.filter(active => CHANNELS[active.tape.channel].group === 'blink');
    if (sketch.length && sketchClock.scene) sketchClock.interrupted += 1;
    sketchClock.scene = null;
    sketch = [];
    sketchUntilMs = 0;
  }

  function settle(): void {
    interruptPerformance();
    tapes = [];
    patterns = [];
    for (const key of CHANNEL_KEYS) {
      springs[key] = { value: targetFor(key), velocity: 0 };
      delete springBlends[key];
    }
    writeOutput();
  }

  /**
   * Overlapping DEPARTURES: what merely follows the face holds its ground for
   * a beat before it starts moving at all. It is a tape pinning the channel
   * to where it currently is — the same mechanism as every other beat.
   */
  function queueLeads(nextTargets: ChannelValues): void {
    if (reducedMotion) return;
    for (const key of CHANNEL_KEYS) {
      if (isDerived(key)) continue;
      const leadMs = leadMsFor(key);
      if (leadMs <= 0) continue;
      const current = springs[key].value;
      if (Math.abs(nextTargets[key] - current) < REST_EPSILON) continue;
      tapes.push({
        tape: {
          channel: key,
          keys: [{ atMs: 0, value: current }],
          durationMs: leadMs,
        },
        elapsedMs: 0,
      });
    }
  }

  /** Something is TRAVELLING: a beat is playing, or a spring has not yet
   * arrived and stopped. */
  function isSettlingNow(): boolean {
    if (reducedMotion) return false;
    // A pattern is a state that keeps MOVING: a search jumping between
    // fixations needs full frames, or its saccades land late.
    if (tapes.length > 0 || sketch.length > 0 || patterns.length > 0) return true;
    for (const key of CHANNEL_KEYS) {
      if (isDerived(key)) continue;
      if (!isSpringAtRest(springs[key], targetFor(key))) return true;
    }
    return false;
  }

  /** Anything still to do? Something travelling, or a loop running. */
  function isAwakeNow(): boolean {
    if (reducedMotion) return false;
    return loops.length > 0 || isSettlingNow();
  }

  /**
   * Everything a NEW EXPRESSION sets in motion, in the order it happens:
   * a reflex clears the floor, the arrival takes its own pace, the willed
   * channels anticipate, the following ones hold, the entrance plays and
   * the state's looping behaviour starts over.
   *
   * Extracted from `setPose` because that method had grown to hold both
   * this and the bookkeeping of four independent "did it change?"
   * questions — two jobs, one function, and the complexity ratchet was
   * right to say so.
   */
  function beginArrival(next: RigPose, nextTargets: ChannelValues): void {
    // A REFLEX pre-empts everything. A startle landing on top of a
    // half-played idle flourish reads as two characters arguing; the beats
    // are dropped so the reflex owns the face outright.
    interruptPerformance();
    expression = next.expression;
    // The mouth's life starts over with the state: a mimic must never land
    // on top of an entrance, and a face that just changed has said enough.
    if (lifeRandom) mouthLifeAtMs = clockMs + drawMouthLifeDelayMs(lifeRandom);
    // Each arrival gets its own pace, so the same emotion twice is never
    // the same performance twice.
    arrivalPace = random ? 1 + (random() - 0.5) * ARRIVAL_JITTER : 1;
    queueAnticipation(nextTargets);
    queueLeads(nextTargets);
    if (!reducedMotion) {
      for (const tape of ARRIVAL_SCRIPTS[next.expression] ?? []) {
        tapes.push({ tape, elapsedMs: 0 });
      }
    }
    patterns = startPatterns(next.expression);
  }

  /** Queue the counter-moves for a pose change. Reflexes get none: a startle
   * that telegraphs itself is not a startle — the classic exception to the
   * anticipation rule. */
  function queueAnticipation(nextTargets: ChannelValues): void {
    if (reducedMotion) return;
    if (DYNAMICS_FOR_EXPRESSION[expression] === 'reflex') return;
    for (const key of CHANNEL_KEYS) {
      const def = CHANNELS[key];
      if (def.snap || !ANTICIPATED_GROUPS.has(def.group)) continue;
      const current = springs[key].value;
      const settings = def.unit === 'deg' ? ANTICIPATION_DEG : ANTICIPATION;
      const tape = anticipationTape(key, current, nextTargets[key], settings);
      if (tape) tapes.push({ tape, elapsedMs: 0 });
    }
  }

  return {
    setContext(next: ActingContext) {
      if (
        Object.keys(NEUTRAL_CONTEXT).every(
          key => next[key as keyof ActingContext] === context[key as keyof ActingContext]
        )
      )
        return;
      const changedActivity = next.activity !== context.activity;
      const takesAttention =
        (changedActivity && next.activity) || (next.responding && !context.responding);
      context = next;
      if (takesAttention) interruptPerformance();
      poseTargets = computeTargets(expression, styleId, family, emphasis);
      if (changedActivity) patterns = startPatterns(expression);
      lastSettling = true;
    },
    setPose(next: RigPose) {
      const nextEmphasis = next.emphasis ?? 1;
      const changedExpression = next.expression !== expression;
      const unchanged =
        !changedExpression &&
        next.styleId === styleId &&
        next.family === family &&
        nextEmphasis === emphasis &&
        (next.responseWeight ?? 1) === responseWeight;
      if (unchanged) return;

      emphasis = nextEmphasis;
      responseWeight = next.responseWeight ?? 1;
      lastSettling = true;
      const nextTargets = computeTargets(next.expression, next.styleId, next.family, emphasis);
      if (changedExpression) beginArrival(next, nextTargets);
      styleId = next.styleId;
      family = next.family;
      poseTargets = nextTargets;
      activeDynamics = scaleDynamics(DYNAMICS_FOR_EXPRESSION[expression], family);
      loops = resolveLoops(expression, family);
      loopsByChannel = indexLoops(loops);
    },

    setGaze(next: Gaze | null, spring?: SpringConfig) {
      gaze = next ? { x: clampGazeAxis(next.x), y: clampGazeAxis(next.y) } : null;
      gazeSpring = spring;
      lastSettling = true;
    },

    play(...next: readonly Tape[]) {
      if (reducedMotion) return;
      for (const tape of next) {
        if ((sketch.length || context.activity) && CHANNELS[tape.channel].group !== 'blink')
          continue;
        tapes.push({ tape, elapsedMs: 0 });
      }
      lastSettling = next.length > 0;
    },

    playSketch,

    isPerforming: () => sketch.length > 0,

    answerIn(delayMs: number) {
      if (!lifeRandom || reducedMotion) return;
      if (!MOUTH_LIFE_EXPRESSIONS.has(expression) || clockMs < sketchUntilMs) return;
      const atMs = clockMs + Math.max(0, delayMs);
      // Never on top of a mimic still playing: one face at a time.
      if (atMs < mouthBusyUntilMs) return;
      mouthLifeAtMs = Math.min(mouthLifeAtMs, atMs);
    },

    sketchClock: () => sketchClock,

    step(dtMs: number): boolean {
      if (reducedMotion) {
        settle();
        return false;
      }
      if (dtMs > 0) {
        // The face's lives are checked before the path is chosen: a mimic
        // or a sketch that starts is a beat, and a beat takes the full path.
        tickSketchLife(dtMs);
        tickMouthLife();
        // Nothing has moved since the last step and nothing is playing: take
        // the cheap path. `lastSettling` is set true by every mutation, so
        // this can never skip a frame that had something to do.
        if (
          !lastSettling &&
          !reducedMotion &&
          tapes.length === 0 &&
          sketch.length === 0 &&
          patterns.length === 0
        ) {
          stepIdle(dtMs);
          return loops.length > 0;
        }
        clockMs += dtMs;
        advanceBeats(dtMs);
        integrateSprings(dtMs);
      }
      writeOutput();
      lastSettling = isSettlingNow();
      return loops.length > 0 || lastSettling;
    },

    values() {
      return output;
    },

    isAwake: isAwakeNow,

    isSettling: () => lastSettling,

    settle,

    setReducedMotion(reduced: boolean) {
      reducedMotion = reduced;
      if (reduced) {
        settle();
        return;
      }
      // Coming back out, the state's own looping behaviour has to be restored:
      // `settle` dropped it, and without this a search that was interrupted by
      // the preference would stay still until the next expression change.
      patterns = startPatterns(expression);
    },
  };
}

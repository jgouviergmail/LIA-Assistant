/** Shared art direction for every skin: temperament, task, then answer release. */
import type { ActivityFamily } from '../activity';
import type { EyeExpression } from '../expression-engine';
import type { ChannelValues } from './channels';
import { absolute, relative } from './choreo';
import type { Tape } from './tape';
import type { DayPhase, WeatherFeeling } from '../environment';
import { ambientChannels } from './ambient';

export interface ActingContext {
  pleasure: number;
  arousal: number;
  dominance: number;
  curiosity: number;
  engagement: number;
  activity: ActivityFamily | null;
  recentFamily: ActivityFamily | null;
  recentWeight: number;
  accomplished: boolean;
  responding: boolean;
  weather: WeatherFeeling | null;
  dayPhase: DayPhase;
}

export const NEUTRAL_CONTEXT: Readonly<ActingContext> = {
  pleasure: 0,
  arousal: 0,
  dominance: 0,
  curiosity: 0.5,
  engagement: 0.5,
  activity: null,
  recentFamily: null,
  recentWeight: 0,
  accomplished: false,
  responding: false,
  weather: null,
  dayPhase: 'noon',
};

export function finiteUnit(value: number, min = -1): number {
  return Number.isFinite(value) ? Math.max(min, Math.min(1, value)) : 0;
}

/** Readable cartoon temperament; authored tasks, lids and silhouettes keep priority. */
export function contextualPose(
  pose: ChannelValues,
  expression: EyeExpression,
  context: ActingContext
): ChannelValues {
  const available =
    !context.activity &&
    !context.responding &&
    ['neutral', 'attentive', 'joy', 'tender', 'bored'].includes(expression);
  const ambient = ambientChannels(context.weather, context.dayPhase, available);
  if (expression === 'sleep' || expression === 'sleepy') return { ...pose, ...ambient };
  const resting = expression === 'neutral' || expression === 'attentive';
  const weight = resting && !context.activity && !context.responding ? 1 : 0.18;
  const pleasure = finiteUnit(context.pleasure) * weight;
  const delight = Math.max(0, pleasure);
  const sadness = Math.max(0, -pleasure);
  const curiosity = (finiteUnit(context.curiosity, 0) - 0.5) * weight;
  const energy = finiteUnit(context.arousal) * weight;
  const confidence = finiteUnit(context.dominance) * weight;
  const engagement = (finiteUnit(context.engagement, 0) - 0.5) * weight;
  const recent = finiteUnit(context.recentWeight, 0) * weight;
  const satisfied = context.accomplished ? recent : 0;
  return {
    ...pose,
    ...ambient,
    mouthCurve: pose.mouthCurve + pleasure * 0.7 + satisfied * 0.18,
    tilt:
      pose.tilt + pleasure * 1.5 + confidence * 1.2 + satisfied * 1.8 - ambient.weatherWind * 2.5,
    mouthSkew:
      pose.mouthSkew +
      confidence * 0.15 +
      curiosity * 0.08 +
      (context.recentFamily === 'calculating' ? recent * 0.08 : 0),
    mouthW: pose.mouthW + pleasure * 0.18 + confidence * 0.05 - ambient.weatherCold * 0.035,
    syL: pose.syL * (1 - delight * 0.16 - sadness * 0.11 + energy * 0.04),
    syR: pose.syR * (1 - delight * 0.14 - sadness * 0.1 + energy * 0.035),
    browRotL: pose.browRotL - sadness * 12 - curiosity * 6 + confidence * 5,
    browRotR: pose.browRotR + sadness * 12 + curiosity * 4 - confidence * 3,
    browArcL:
      pose.browArcL +
      delight * 0.35 +
      curiosity * 0.38 +
      (context.recentFamily === 'creating' ? recent * 0.12 : 0),
    browArcR: pose.browArcR + delight * 0.28 + curiosity * 0.26,
    browYL: pose.browYL - delight * 0.05 - energy * 0.045 - engagement * 0.03,
    browYR: pose.browYR - delight * 0.035 - energy * 0.035 - engagement * 0.025,
  };
}

const SOFT = { frequency: 1.5, damping: 1 };

/** A thought is a look, a held consideration, then a soft return. No chewing. */
export function thoughtPattern(random: () => number): Tape[] {
  const side = random() < 0.5 ? -1 : 1;
  const hold = 2500 + random() * 2500;
  const duration = hold + 4000 + random() * 2000;
  return [
    absolute(
      'gazeX',
      [
        [0, 0],
        [1800, side * 0.28],
        [hold + 2100, 0],
      ],
      duration,
      SOFT
    ),
    absolute(
      'gazeY',
      [
        [0, -0.15],
        [1600, -0.23],
        [hold + 1900, -0.1],
      ],
      duration,
      SOFT
    ),
    relative(
      'browYL',
      [
        [0, 0],
        [2000, -0.008],
        [hold + 2300, 0],
      ],
      duration,
      SOFT
    ),
  ];
}

/** Tool families differ in attention and pose, without miming an unproven effect. */
export function activityPattern(family: ActivityFamily, random: () => number): Tape[] {
  const side = random() < 0.5 ? -1 : 1;
  const hold = 2200 + random() * 2200;
  const duration = hold + 3500;
  const looks: Record<ActivityFamily, readonly [number, number]> = {
    reading: [0.45, 0.22],
    organizing: [0.25, 0.3],
    communicating: [0.1, 0],
    calculating: [0.25, -0.28],
    creating: [0.4, -0.18],
    exploring: [0.65, 0.08],
    generic: [0.2, -0.1],
  };
  const [x, y] = looks[family];
  return [
    absolute(
      'gazeX',
      [
        [0, 0],
        [1000, x * side],
        [hold, -x * side * 0.4],
        [duration - 900, 0],
      ],
      duration,
      SOFT
    ),
    absolute(
      'gazeY',
      [
        [0, 0],
        [850, y],
        [duration - 1100, 0],
      ],
      duration,
      SOFT
    ),
    relative(
      'browArcL',
      [
        [0, 0],
        [1300, family === 'creating' ? 0.12 : 0.045],
        [duration - 700, 0],
      ],
      duration,
      SOFT
    ),
    relative(
      'mouthSkew',
      [
        [0, 0],
        [1700, family === 'calculating' ? side * 0.035 : 0],
        [duration - 700, 0],
      ],
      duration,
      SOFT
    ),
  ];
}

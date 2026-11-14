/** Shared art direction for every skin: temperament, task, then answer release. */
import type { ActivityFamily } from '../activity';
import type { EyeExpression } from '../expression-engine';
import type { ChannelValues } from './channels';
import { absolute, relative } from './choreo';
import type { SpringConfig } from './spring';
import type { Tape } from './tape';
import type { DayPhase, SkyCover, WeatherFeeling } from '../environment';
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
  /** The face follows text as it is written: the answer on screen, or the
   * person's own typing. Its spontaneous life stands aside; its pose does not
   * change — following is not a task. */
  attending: boolean;
  weather: WeatherFeeling | null;
  weatherFlags?: readonly WeatherFeeling[];
  /** The sky of an ordinary day, drawn by day: never a condition it plays. */
  sky: SkyCover | null;
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
  attending: false,
  weather: null,
  weatherFlags: [],
  sky: null,
  dayPhase: 'noon',
};

export function finiteUnit(value: number, min = -1): number {
  return Number.isFinite(value) ? Math.max(min, Math.min(1, value)) : 0;
}

/**
 * Whether the face is taken by an answer's own expression. A factual answer
 * earns `neutral` — the face the character rests on — so it keeps the rest
 * smile and the temperament (measured on the bench: the smile went from 0.26
 * to 0.12 the moment such an answer was delivered).
 */
export function answering(context: ActingContext, expression: EyeExpression): boolean {
  return context.responding && expression !== 'neutral';
}

/** Readable cartoon temperament; authored tasks, lids and silhouettes keep priority. */
export function contextualPose(
  pose: ChannelValues,
  expression: EyeExpression,
  context: ActingContext
): ChannelValues {
  const ambient = ambientChannels(
    context.weather,
    context.dayPhase,
    true,
    context.weatherFlags,
    context.sky
  );
  if (expression === 'sleep' || expression === 'sleepy') return { ...pose, ...ambient };
  const resting = expression === 'neutral' || expression === 'attentive';
  const weight = resting && !context.activity && !answering(context, expression) ? 1 : 0.18;
  const pleasure = finiteUnit(context.pleasure) * weight;
  const delight = Math.max(0, pleasure);
  const sadness = Math.max(0, -pleasure);
  const curiosity = (finiteUnit(context.curiosity, 0) - 0.5) * weight;
  const energy = finiteUnit(context.arousal) * weight;
  const confidence = finiteUnit(context.dominance) * weight;
  const engagement = (finiteUnit(context.engagement, 0) - 0.5) * weight;
  const recent = finiteUnit(context.recentWeight, 0) * weight;
  const satisfied = context.accomplished ? recent : 0;
  // The wind is not a mood: like the lean it gives the head, the squint it
  // gives the eyes holds through work and through an answer.
  const squint = ambient.weatherWind * WIND_SQUINT;
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
    syL: pose.syL * (1 - delight * 0.16 - sadness * 0.11 + energy * 0.04 - squint),
    syR: pose.syR * (1 - delight * 0.14 - sadness * 0.1 + energy * 0.035 - squint),
    browRotL: pose.browRotL - sadness * 12 - curiosity * 6 + confidence * 5,
    browRotR: pose.browRotR + sadness * 12 + curiosity * 4 - confidence * 3,
    browArcL:
      pose.browArcL +
      delight * 0.35 +
      curiosity * 0.38 +
      (context.recentFamily === 'creating' ? recent * 0.12 : 0),
    browArcR: pose.browArcR + delight * 0.28 + curiosity * 0.26,
    browYL: pose.browYL - delight * 0.05 - energy * 0.045 - engagement * 0.03 + squint * WIND_BROW,
    browYR:
      pose.browYR - delight * 0.035 - energy * 0.035 - engagement * 0.025 + squint * WIND_BROW,
  };
}

/** How much of their height the eyes give up to a strong wind, and how far
 * the brows come down with them, in em per unit of squint. */
const WIND_SQUINT = 0.14;
const WIND_BROW = 0.09;

const SOFT = { frequency: 1.5, damping: 1 };

/** Weather that FALLS: the only kind there is something to look up at. */
const SKY_WEATHER: ReadonlySet<WeatherFeeling> = new Set(['rain', 'storm', 'snow']);

/** The weather a face would look up at, or null — cold, wind, fog and heat
 * are felt, not watched. */
export function skyWeather(weather: WeatherFeeling | null): WeatherFeeling | null {
  return weather && SKY_WEATHER.has(weather) ? weather : null;
}

/**
 * It has started to rain, or to snow: the eyes go up to it, the brows with
 * them, and come back. One look — the head follows the eyes by itself.
 */
export function skyGlanceTapes(random: () => number): Tape[] {
  const side = random() < 0.5 ? -1 : 1;
  const held = 700 + random() * 400;
  const duration = held + 500;
  return [
    absolute(
      'gazeY',
      [
        [0, -0.72],
        [held, 0],
      ],
      duration,
      SOFT_LOOK
    ),
    absolute(
      'gazeX',
      [
        [0, side * 0.14],
        [held, 0],
      ],
      duration,
      SOFT_LOOK
    ),
    relative(
      'browYL',
      [
        [60, -0.03],
        [held, 0],
      ],
      duration,
      SOFT_LOOK
    ),
    relative(
      'browYR',
      [
        [100, -0.027],
        [held + 40, 0],
      ],
      duration + 40,
      SOFT_LOOK
    ),
  ];
}

/** A look, not a jump: quicker than a thought, slower than a saccade. */
const SOFT_LOOK = { frequency: 2.6, damping: 1 };

/**
 * The attitudes a thought takes, in the order a long one goes through them:
 * the eyes up and away, then down and inward, then the head to one side. A
 * wait lasts half a minute at the median, and one look held for all of it is
 * a face that stopped; three, never twice the same in a row, is one thinking.
 */
const THOUGHT_ATTITUDES = ['up', 'inward', 'tilted'] as const;

/**
 * A thought is a look, a held consideration, then a soft return. No chewing.
 *
 * `turn` counts the thoughts of ONE stretch of thinking: the rig restarts it
 * with each new thought, so a thought always opens up and away.
 */
export function thoughtPattern(random: () => number, turn = 0): Tape[] {
  const side = random() < 0.5 ? -1 : 1;
  const hold = 2500 + random() * 2500;
  const duration = hold + 4000 + random() * 2000;
  const attitude = THOUGHT_ATTITUDES[Math.max(0, Math.floor(turn)) % THOUGHT_ATTITUDES.length];
  if (attitude === 'inward')
    return [
      absolute(
        'gazeX',
        [
          [0, 0],
          [1500, side * 0.2],
          [hold + 2000, 0],
        ],
        duration,
        SOFT
      ),
      absolute(
        'gazeY',
        [
          [0, 0.05],
          [1400, 0.16],
          [hold + 1900, 0.02],
        ],
        duration,
        SOFT
      ),
    ];
  if (attitude === 'tilted')
    return [
      // The head goes one way and the eyes the other: a weighing.
      relative(
        'tilt',
        [
          [0, 0],
          [900, side * 2.4],
          [hold + 1700, 0],
        ],
        duration,
        SOFT
      ),
      absolute(
        'gazeX',
        [
          [0, 0],
          [1700, -side * 0.22],
          [hold + 2100, 0],
        ],
        duration,
        SOFT
      ),
      absolute(
        'gazeY',
        [
          [0, -0.1],
          [1500, -0.2],
          [hold + 1900, -0.08],
        ],
        duration,
        SOFT
      ),
    ];
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

/** A fixation jumps to the next word: quicker than a look, gentler than a search. */
const READING: SpringConfig = { frequency: 5.2, damping: 1 };
/** Half the width of a line, in gaze units: the eyes travel a page, and the
 * head, which follows them, stays where it is. */
const READING_HALF_LINE = 0.4;
/** How low the first line sits, and how much lower each next one. */
const READING_FIRST_LINE = 0.13;
const READING_LINE_STEP = 0.07;
/** How far the head bows to the page, and stays: about the first line. */
const READING_BOW = 0.14;

/**
 * Reading, as eyes do it: short rests walking a line from left to right, now
 * and then a second look at a word, a quick return to the start of the next
 * line, a little lower — and, the page read, the eyes up from it for a moment
 * before the next one. Every page is drawn anew: the rig asks again each time
 * the pattern wraps, so no two are read alike.
 *
 * The HEAD does not read. It follows the gaze everywhere else, which is right
 * for a look and wrong for a line: a head that sweeps each one is a head
 * shaking (measured: 13.3 units of yaw in twenty seconds, against 5.2 for an
 * exploration). It bows to the page and stays, and comes up with the eyes.
 */
function readingGaze(random: () => number): Tape[] {
  const across: [number, number][] = [];
  const down: [number, number][] = [];
  const lines = 2 + Math.floor(random() * 2);
  let at = 0;
  for (let line = 0; line < lines; line += 1) {
    const stops = 3 + Math.floor(random() * 3);
    const again = random() < 0.25 ? 1 + Math.floor(random() * (stops - 2)) : -1;
    down.push([at, READING_FIRST_LINE + line * READING_LINE_STEP + (random() - 0.5) * 0.016]);
    for (let stop = 0; stop < stops; stop += 1) {
      const along = (stop / (stops - 1)) * 2 - 1;
      const x = along * READING_HALF_LINE + (random() - 0.5) * 0.06;
      across.push([at, x]);
      at += 230 + random() * 190;
      if (stop === again) {
        across.push([at, x - 0.11]);
        at += 230 + random() * 120;
      }
    }
  }
  // The page is read: the eyes come up from it, and hold the time to take it in.
  const side = random() < 0.5 ? -1 : 1;
  across.push([at, side * 0.08]);
  down.push([at, -0.04]);
  const duration = at + 600 + random() * 500;
  return [
    absolute('gazeX', across, duration, READING),
    absolute('gazeY', down, duration, READING),
    absolute('headYaw', [[0, 0]], duration, SOFT),
    absolute(
      'headPitch',
      [
        [0, READING_BOW],
        [at, 0.02],
      ],
      duration,
      SOFT
    ),
  ];
}

/** Tool families differ in attention and pose, without miming an unproven effect. */
export function activityPattern(family: ActivityFamily, random: () => number): Tape[] {
  if (family === 'reading') return readingGaze(random);
  const side = random() < 0.5 ? -1 : 1;
  const hold = 2200 + random() * 2200;
  const duration = hold + 3500;
  const looks: Record<Exclude<ActivityFamily, 'reading'>, readonly [number, number]> = {
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

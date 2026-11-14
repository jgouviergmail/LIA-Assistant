/**
 * Weather the character LIVES (ADR-294, follow-up of 2026-11-13): four scenes
 * the owner chose on the bench, played like the catalogue's own.
 *
 *  - The first drop of a rain lands on the head: a flinch, a look up, and only
 *    then the umbrella (the rain is held back until the drop has landed), then
 *    relief. It replaces the look at the sky for rain.
 *  - The first flake of a snow is pursued by the eyes down to the root of the
 *    nose (the one place on every face where it covers no eye, brow or mouth):
 *    an « oh », it lands, a blink, a delighted smile. It replaces the look at the
 *    sky for snow. A storm keeps the look.
 *  - In the cold, a shiver: hunched, teeth chattering, brows knit, an exhale.
 *  - On a clear, mild day, by day, the sun on the face: eyes closed, a content
 *    smile, two slow breaths.
 *
 * The drop and the flake are drawn by the sheet from two channels the scenes
 * drive (`weatherDrop`, `weatherFlake`, announced `drop` and `flake`): a prop with
 * no scene has no box. A scene that carries a prop is never warped, because the
 * prop and the face meet on one beat (`carriesProp`).
 */
import type { DayPhase, SkyCover, WeatherFeeling } from '../environment';
import { absolute, bothSides, mirrored, relative } from './choreo';
import type { SpringConfig } from './spring';
import type { Tape } from './tape';

export const WEATHER_SCENES = [
  'weather-first-drop',
  'weather-catch-flake',
  'weather-shiver',
  'weather-sun-bask',
] as const;

export type WeatherSceneName = (typeof WEATHER_SCENES)[number];

/** Whether a scene's name is one of the weather's. */
export function isWeatherSceneName(name: string): name is WeatherSceneName {
  return WEATHER_SCENES.some(candidate => candidate === name);
}

/** When the drop meets the head, in ms of its scene: the flinch is on this beat. */
export const DROP_LANDS_MS = 560;
/** How long the landed drop splashes before it is gone. */
const DROP_SPLASH_MS = 120;
/** When the flake settles on the nose; the blink and the smile follow it. */
export const FLAKE_LANDS_MS = 2200;
/** How long the settled flake stays before it melts away. */
const FLAKE_REST_MS = 200;
/** The rain the first drop announces is held back until the face has felt it. */
export const RAIN_HELD_MS = 1000;

const BLINK: SpringConfig = { frequency: 6.2, damping: 0.72 };
const SLOW: SpringConfig = { frequency: 2.2, damping: 0.92 };
const SOFT: SpringConfig = { frequency: 3.0, damping: 0.95 };
const QUICK: SpringConfig = { frequency: 5.5, damping: 0.8 };
const LOOK: SpringConfig = { frequency: 3.4, damping: 1 };
const SHAKE: SpringConfig = { frequency: 13, damping: 0.45 };

/** Both lids, the right one a beat behind, as a blink is. */
function lids(
  keys: readonly (readonly [number, number])[],
  durationMs: number,
  spring: SpringConfig
): Tape[] {
  return [
    absolute('blinkL', keys, durationMs, spring),
    absolute(
      'blinkR',
      keys.map(([at, value]) => [at + 50, value] as const),
      durationMs + 50,
      spring
    ),
  ];
}

/** The eyes following a moving thing: the target moves between keys, the look's
 * spring still owns the eyes. */
function pursuit(
  channel: 'gazeX' | 'gazeY',
  keys: readonly (readonly [number, number])[],
  durationMs: number
): Tape {
  return { ...relative(channel, keys, durationMs, LOOK), interpolation: 'linear' };
}

/** A prop's path: 0 where it appears, 1 where it lands, then gone. */
function propPath(
  channel: 'weatherDrop' | 'weatherFlake',
  landsMs: number,
  afterMs: number,
  settled: number
): Tape {
  return {
    channel,
    keys: [
      { atMs: 0, value: 0 },
      { atMs: landsMs, value: 1 },
      { atMs: landsMs + afterMs, value: settled },
      { atMs: landsMs + afterMs + 1, value: 0 },
    ],
    durationMs: landsMs + afterMs + 1,
    interpolation: 'linear',
  };
}

/** The first drop lands on the head: a flinch, a look up, the umbrella, relief. */
function firstDrop(): Tape[] {
  return [
    propPath('weatherDrop', DROP_LANDS_MS, DROP_SPLASH_MS, 1.1),
    // Nothing of the rain shows before the face has felt it: then the cloud
    // comes and the umbrella opens, as the face looks up at them.
    absolute('weatherRain', [[0, 0]], RAIN_HELD_MS),
    ...lids(
      [
        [DROP_LANDS_MS, 1],
        [DROP_LANDS_MS + 140, 0],
      ],
      950,
      BLINK
    ),
    relative(
      'headPitch',
      [
        [0, 0],
        [DROP_LANDS_MS, 0.1],
        [760, 0.08],
        [1000, -0.11],
        [1900, -0.11],
        [2400, 0],
      ],
      2800,
      QUICK
    ),
    absolute(
      'bodySy',
      [
        [DROP_LANDS_MS, 0.955],
        [780, 1.01],
        [1000, 1],
      ],
      1300,
      QUICK
    ),
    ...bothSides(
      'browY',
      [
        [DROP_LANDS_MS + 20, -0.045],
        [1100, -0.03],
        [1900, -0.01],
        [2400, 0],
      ],
      2700,
      QUICK
    ),
    relative(
      'gazeY',
      [
        [0, 0],
        [950, -0.75],
        [1900, -0.7],
        [2300, 0],
      ],
      2600,
      LOOK
    ),
    relative(
      'mouthOpen',
      [
        [DROP_LANDS_MS + 40, 0.05],
        [1000, 0],
      ],
      1200,
      QUICK
    ),
    relative(
      'mouthCurve',
      [
        [2000, 0.09],
        [3000, 0.04],
      ],
      3500,
      SOFT
    ),
    ...bothSides(
      'sy',
      [
        [2000, -0.14],
        [3000, -0.06],
      ],
      3500,
      SOFT
    ),
    ...bothSides(
      'oy',
      [
        [2000, -11],
        [3000, -5],
      ],
      3500,
      SOFT
    ),
  ];
}

/** A flake falls; the eyes follow it down to the nose, an « oh », it lands, a delighted smile. */
function catchFlake(): Tape[] {
  return [
    propPath('weatherFlake', FLAKE_LANDS_MS, FLAKE_REST_MS, 1),
    // The eyes PURSUE it: a moving target, a beat ahead so the spring is there
    // when the flake is — at the root of the nose as it settles, the middle of
    // the face, just above where the eyes rest.
    pursuit(
      'gazeY',
      [
        [0, -0.72],
        [600, -0.52],
        [1200, -0.34],
        [1650, -0.2],
        [FLAKE_LANDS_MS - 250, -0.12],
        [2700, -0.04],
      ],
      3100
    ),
    pursuit(
      'gazeX',
      [
        [0, -0.38],
        [700, -0.12],
        [1300, -0.22],
        [FLAKE_LANDS_MS - 250, -0.02],
      ],
      2700
    ),
    relative(
      'headPitch',
      [
        [0, -0.1],
        [1450, -0.02],
        [FLAKE_LANDS_MS - 50, 0.05],
        [2800, 0],
      ],
      3200,
      LOOK
    ),
    relative(
      'mouthOpen',
      [
        [500, 0.07],
        [FLAKE_LANDS_MS - 100, 0.07],
        [FLAKE_LANDS_MS + 100, 0],
      ],
      2500,
      SOFT
    ),
    relative(
      'mouthW',
      [
        [500, -0.12],
        [FLAKE_LANDS_MS - 100, -0.12],
        [FLAKE_LANDS_MS + 100, 0],
      ],
      2500,
      SOFT
    ),
    ...lids(
      [
        [FLAKE_LANDS_MS + 40, 1],
        [FLAKE_LANDS_MS + 220, 0.35],
        [2700, 0],
      ],
      3000,
      QUICK
    ),
    relative(
      'mouthCurve',
      [
        [FLAKE_LANDS_MS + 150, 0.13],
        [3400, 0.05],
      ],
      3900,
      SOFT
    ),
    ...bothSides(
      'sy',
      [
        [FLAKE_LANDS_MS + 150, -0.22],
        [3400, -0.08],
      ],
      3900,
      SOFT
    ),
    ...bothSides(
      'oy',
      [
        [FLAKE_LANDS_MS + 150, -17],
        [3400, -6],
      ],
      3900,
      SOFT
    ),
    absolute(
      'bodySy',
      [
        [FLAKE_LANDS_MS + 100, 1.035],
        [FLAKE_LANDS_MS + 350, 0.985],
        [FLAKE_LANDS_MS + 600, 1],
      ],
      FLAKE_LANDS_MS + 900,
      QUICK
    ),
  ];
}

/** Brrr: the body shivers, hunched, teeth chattering, brows knit — then an exhale. */
function shiver(): Tape[] {
  const roll: [number, number][] = [[0, 0]];
  const chatter: [number, number][] = [[0, 0]];
  for (let at = 60, side = 1; at <= 900; at += 55, side = -side)
    roll.push([at, side * 1.7 * (1 - at / 1150)]);
  roll.push([960, 0]);
  for (let at = 80, open = 1; at <= 860; at += 65, open = 1 - open) chatter.push([at, open * 0.05]);
  chatter.push([900, 0]);
  return [
    relative('bodyRoll', roll, 1300, SHAKE),
    absolute(
      'bodySy',
      [
        [0, 0.965],
        [1000, 0.97],
        [1450, 1],
      ],
      1800,
      SOFT
    ),
    absolute(
      'bodySx',
      [
        [0, 1.02],
        [1000, 1.018],
        [1450, 1],
      ],
      1800,
      SOFT
    ),
    relative('mouthOpen', chatter, 1100, QUICK),
    relative(
      'mouthW',
      [
        [0, -0.08],
        [1000, -0.06],
        [1400, 0],
      ],
      1700,
      SOFT
    ),
    ...mirrored(
      'browRot',
      [
        [0, 6],
        [1100, 5],
        [1500, 0],
      ],
      1800,
      SOFT
    ),
    ...bothSides(
      'browY',
      [
        [0, 0.012],
        [1100, 0.01],
        [1500, 0],
      ],
      1800,
      SOFT
    ),
    ...bothSides(
      'sy',
      [
        [0, -0.18],
        [1100, -0.14],
        [1500, 0],
      ],
      1800,
      SOFT
    ),
    relative(
      'mass',
      [
        [1250, -0.016],
        [1800, 0],
      ],
      2200,
      SLOW
    ),
  ];
}

/** The sun on the face: eyes close, face up, a content smile, two slow breaths. */
function sunBask(): Tape[] {
  return [
    ...lids(
      [
        [250, 0],
        [900, 0.9],
        [3000, 0.9],
        [3500, 0],
      ],
      3900,
      SLOW
    ),
    relative(
      'headPitch',
      [
        [0, 0],
        [900, -0.13],
        [3000, -0.13],
        [3700, 0],
      ],
      4100,
      SLOW
    ),
    relative(
      'mouthCurve',
      [
        [600, 0.11],
        [3000, 0.11],
        [3700, 0.02],
      ],
      4200,
      SLOW
    ),
    ...bothSides(
      'browY',
      [
        [600, 0.008],
        [3000, 0.008],
        [3600, 0],
      ],
      4000,
      SLOW
    ),
    relative(
      'mass',
      [
        [900, 0.016],
        [1800, 0],
        [2600, 0.016],
        [3500, 0],
      ],
      3900,
      SLOW
    ),
  ];
}

const SCENES: Readonly<Record<WeatherSceneName, () => Tape[]>> = {
  'weather-first-drop': firstDrop,
  'weather-catch-flake': catchFlake,
  'weather-shiver': shiver,
  'weather-sun-bask': sunBask,
};

/** A weather scene's tapes, as authored: a character's own pace is applied later. */
export function weatherSceneTapes(name: WeatherSceneName): Tape[] {
  return SCENES[name]();
}

/** Scenes whose prop meets the face on one beat: never warped. */
const PROP_SCENES: ReadonlySet<WeatherSceneName> = new Set([
  'weather-first-drop',
  'weather-catch-flake',
]);

export function carriesProp(name: string): boolean {
  return isWeatherSceneName(name) && PROP_SCENES.has(name);
}

/** What the cold does to a face at rest: it shivers, and it sneezes. */
const CHILLED: ReadonlySet<WeatherFeeling> = new Set(['cold', 'freezing']);

export function isChilled(conditions: readonly WeatherFeeling[]): boolean {
  return conditions.some(feeling => CHILLED.has(feeling));
}

/**
 * The scene that greets weather starting to fall: the first drop for rain, a
 * caught flake for snow. A storm is looked at (`null`): one drop is not news in it.
 */
export function arrivalScene(sky: WeatherFeeling): WeatherSceneName | null {
  if (sky === 'rain') return 'weather-first-drop';
  if (sky === 'snow') return 'weather-catch-flake';
  return null;
}

/**
 * The resting scenes the observed weather allows: a shiver in the cold; the sun
 * on the face on a clear day, by day, when nothing else is felt (no heat, no
 * wind, no cold — a mild sun is the one a face turns to).
 */
export function restingWeatherScenes(
  conditions: readonly WeatherFeeling[],
  sky: SkyCover | null,
  phase: DayPhase
): readonly WeatherSceneName[] {
  if (isChilled(conditions)) return ['weather-shiver'];
  if (sky === 'clear' && phase !== 'night' && conditions.length === 0) return ['weather-sun-bask'];
  return [];
}

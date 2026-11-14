/** Character direction changes performances, never the native clock or emotion. */
import type { RigEyeStyleId } from '../eye-styles';
import type { EyeExpression } from '../expression-engine';
import type { WeatherFeeling } from '../environment';
import type { ChannelValues } from './channels';
import { SKETCHES, type SketchName } from './sketches';
import { isChilled, type WeatherSceneName } from './weather-scenes';

export type RigCharacterId =
  | RigEyeStyleId
  | 'spirit'
  | 'moss'
  | 'lumen'
  | 'nimbo'
  | 'orbit'
  | 'bip'
  | 'boulon'
  | 'oscar';
export interface ActingProfile {
  readonly identity: RigCharacterId;
  readonly signature: SketchName;
  readonly repertoire: readonly SketchName[];
  readonly pace: number;
  readonly bodyAmplitude: number;
  readonly faceAmplitude: number;
  /** Compression is material-specific, independently from root travel. */
  readonly elasticity: number;
}

const CASING_ELASTICITY = 0.12;
const QUIET = ['double-take', 'suspicious'] as const;
const ALERT = ['double-take', 'body-startle'] as const;
const SOFT = ['fly', 'body-doze', 'body-balloon'] as const;
const DELIBERATE = ['suspicious', 'body-bow'] as const;

function profile(
  identity: RigCharacterId,
  signature: SketchName,
  repertoire: readonly SketchName[],
  pace = 1,
  bodyAmplitude = 1,
  faceAmplitude = 1,
  elasticity = CASING_ELASTICITY
): ActingProfile {
  return { identity, signature, repertoire, pace, bodyAmplitude, faceAmplitude, elasticity };
}
const PROFILES = {
  cozmo: profile('cozmo', 'double-take', ALERT, 0.94, 0.7),
  capsules: profile('capsules', 'body-doze', QUIET, 1.04, 0.62),
  billes: profile('billes', 'body-balloon', SOFT, 1.02, 0.82),
  amande: profile('amande', 'suspicious', DELIBERATE, 1.08, 0.58),
  traits: profile('traits', 'double-take', QUIET, 0.96, 0.55, 0.9),
  anneaux: profile('anneaux', 'fly', QUIET, 1, 0.62),
  spirit: profile('spirit', 'fly', SOFT, 1.04, 0.92, 0.98, 0.65),
  moss: profile('moss', 'body-doze', SOFT, 1.08, 0.78, 0.94, 0.65),
  lumen: profile('lumen', 'body-balloon', SOFT, 1.02, 0.88, 1.02, 0.65),
  nimbo: profile('nimbo', 'body-sneeze', SOFT, 1.03, 0.92, 1.04, 1),
  orbit: profile('orbit', 'body-balloon', QUIET, 1.06, 0.86, 1, 0.15),
  bip: profile('bip', 'body-hops', ALERT, 0.97, 0.94, 1.04),
  boulon: profile('boulon', 'body-startle', ALERT, 0.91, 0.74, 1.04, 0.14),
  oscar: profile('oscar', 'body-bow', DELIBERATE, 1.12, 0.65, 0.94, 0.09),
} satisfies Record<RigCharacterId, ActingProfile>;

interface LimbArticulation {
  readonly accent: number;
  readonly wristLag: number;
  readonly recovery: number;
}

const SOFT_HAND: LimbArticulation = { accent: 0.9, wristLag: 105, recovery: 1.08 };
const LIMB_ARTICULATION: Partial<Record<RigCharacterId, LimbArticulation>> = {
  bip: { accent: 1, wristLag: 75, recovery: 0.94 },
  boulon: { accent: 0.84, wristLag: 42, recovery: 0.8 },
  oscar: { accent: 0.73, wristLag: 135, recovery: 1.16 },
};

/** Delays are part of the authored beat on the existing native clock. */
export function limbArticulation(identity?: RigCharacterId): LimbArticulation {
  return (identity && LIMB_ARTICULATION[identity]) || SOFT_HAND;
}

export function resolveActingProfile(
  characterId: RigCharacterId | undefined,
  styleId: RigEyeStyleId
): ActingProfile {
  return PROFILES[characterId ?? styleId];
}

const REST_SMILES: Partial<Record<RigCharacterId, readonly [curve: number, open: number]>> = {
  spirit: [0.28, 0.025],
  moss: [0.27, 0.02],
  lumen: [0.29, 0.03],
  nimbo: [0.36, 0.045],
  orbit: [0.34, 0.04],
  boulon: [0.35, 0.04],
  oscar: [0.36, 0.04],
};

/** A material's quiet rest yields to emotion; native recipes and width stay authored. */
export function characterNeutralPose(
  pose: ChannelValues,
  expression: EyeExpression,
  characterId?: RigCharacterId,
  pleasure = 0
): ChannelValues {
  const smile = characterId ? REST_SMILES[characterId] : undefined;
  if (expression !== 'neutral' || !smile) return pose;
  const influence = 1 - (Number.isFinite(pleasure) ? Math.min(1, Math.abs(pleasure)) : 0);
  return {
    ...pose,
    mouthCurve: pose.mouthCurve + (smile[0] - pose.mouthCurve) * influence,
    mouthOpen: pose.mouthOpen + (smile[1] - pose.mouthOpen) * influence,
  };
}

/** Sleep performances share one policy for autonomous and explicitly cued scenes. */
const SLEEP_SKETCHES: ReadonlySet<SketchName> = new Set([
  'doze-and-snap',
  'body-doze',
  'yawn-stretch',
]);

export function canPlaySketch(name: SketchName, allowSleep: boolean): boolean {
  return allowSleep || !SLEEP_SKETCHES.has(name);
}

/**
 * The favorite is more frequent; allowed scenes remain reachable and memory wins.
 * In the cold a sneeze is as likely as a favorite: the weather is observed, the
 * scene is the catalogue's own, and it still never plays twice in a row. A scene
 * the weather offers (`restingWeatherScenes`: a shiver in the cold, the sun on a
 * clear mild day) joins the draw as likely as a favorite, and only then.
 */
export function pickActingSketch(
  profile: ActingProfile,
  random: () => number,
  recent: readonly SketchName[] = [],
  allowSleep = true,
  weather: readonly WeatherFeeling[] = [],
  offered: readonly WeatherSceneName[] = []
): SketchName {
  const chilled = isChilled(weather);
  const catalogue = [...SKETCHES.filter(name => canPlaySketch(name, allowSleep)), ...offered];
  const available = catalogue.filter(name => !recent.includes(name));
  const pool = available.length ? available : catalogue;
  const weight = (name: SketchName) => {
    if (name === profile.signature || (chilled && name === 'sneeze')) return 8;
    if (offered.some(scene => scene === name)) return 8;
    return profile.repertoire.includes(name) ? 3 : 1;
  };
  const draw = random();
  let cursor =
    (Number.isFinite(draw) ? Math.max(0, Math.min(1, draw)) : 0) *
    pool.reduce((total, name) => total + weight(name), 0);
  for (const name of pool) {
    cursor -= weight(name);
    if (cursor < 0) return name;
  }
  return pool[pool.length - 1];
}

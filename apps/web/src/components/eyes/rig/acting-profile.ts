/** Character direction changes performances, never the native clock or emotion. */
import type { RigEyeStyleId } from '../eye-styles';
import type { EyeExpression } from '../expression-engine';
import type { ChannelValues } from './channels';
import { SKETCHES, type SketchName } from './sketches';

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
  readonly pace: number;
  readonly bodyAmplitude: number;
  readonly faceAmplitude: number;
}

function profile(
  identity: RigCharacterId,
  signature: SketchName,
  pace = 1,
  bodyAmplitude = 1,
  faceAmplitude = 1
): ActingProfile {
  return { identity, signature, pace, bodyAmplitude, faceAmplitude };
}
const PROFILES = {
  cozmo: profile('cozmo', 'double-take', 0.98),
  capsules: profile('capsules', 'body-doze', 1.02, 0.94),
  billes: profile('billes', 'body-balloon'),
  amande: profile('amande', 'brow-groove', 1.02, 0.92),
  traits: profile('traits', 'body-jig', 0.98),
  anneaux: profile('anneaux', 'dizzy'),
  smiley: profile('smiley', 'body-hops'),
  spirit: profile('spirit', 'fly', 1.02, 0.96, 0.98),
  moss: profile('moss', 'body-doze', 1.02, 0.92, 0.94),
  lumen: profile('lumen', 'body-jig', 0.98, 0.98, 1.02),
  nimbo: profile('nimbo', 'body-sneeze', 1, 0.96, 1.04),
  orbit: profile('orbit', 'body-balloon', 1.02, 0.96),
  bip: profile('bip', 'body-hops', 1, 0.98, 1.04),
  boulon: profile('boulon', 'body-roll', 1, 0.94, 1.04),
  oscar: profile('oscar', 'body-bow', 1.02, 0.9, 0.94),
} satisfies Record<RigCharacterId, ActingProfile>;

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

/** The favorite is more frequent; every other scene remains reachable and memory wins. */
export function pickActingSketch(
  profile: ActingProfile,
  random: () => number,
  recent: readonly SketchName[] = []
): SketchName {
  const available = SKETCHES.filter(name => !recent.includes(name));
  const pool = available.length ? available : SKETCHES;
  const weight = (name: SketchName) => (name === profile.signature ? 6 : 1);
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

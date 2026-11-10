/** One phase table drives a scene's body, limbs and face on the native tape clock. */
import type { BodyMotionSpace } from '../body-motion-geometry';
import { CHANNELS, type ChannelKey } from './channels';
import { absolute, HEAD_FOLLOW_X_EM, relative, type Keys } from './choreo';
import type { SpringConfig } from './spring';
import type { Tape } from './tape';
import type { RigCharacterId } from './acting-profile';

type Pair = readonly [number, number];
interface SceneAccent {
  /** Eye squash, brow height, smile and mouth opening, relative to the facial pose. */
  face?: readonly [number, number, number, number];
  pitch?: number;
  blinkL?: number;
  blinkR?: number;
  gaze?: number;
  arms?: Pair;
  wrists?: Pair;
}
export interface ScenePose extends SceneAccent {
  x?: number;
  y?: number;
  roll?: number;
  shape?: Pair;
  support?: number;
  side?: number;
  legs?: Pair;
  feet?: Pair;
  blink?: number;
  /** Identity accents belong to this phase, not a second timed score. */
  character?: Partial<Record<RigCharacterId, SceneAccent>>;
  /** The flight curve and contact transitions share these phase boundaries. */
  flight?: { duration: number; height: number };
}
export type ScenePhase = readonly [atMs: number, pose: ScenePose];
export interface BodyScene {
  duration: number;
  phases: readonly ScenePhase[];
  spring?: SpringConfig;
}

const BODY = { frequency: 4.6, damping: 1 };
const FLIGHT = { frequency: 7.5, damping: 1 };
const LIMB = { frequency: 3.8, damping: 1 };
const DISTAL = { frequency: 3.1, damping: 1 };
const FACE = { frequency: 3.8, damping: 0.9 };
const FOLLOW = { frequency: 2.4, damping: 0.9 };
const BODY_KEYS = [
  'bodyX',
  'bodyY',
  'bodyRoll',
  'bodySx',
  'bodySy',
  'bodySupport',
  'bodySupportSide',
] as const;
const DISTAL_KEYS: ReadonlySet<ChannelKey> = new Set(['wristL', 'wristR']);
const LIMB_KEYS: ReadonlySet<ChannelKey> = new Set([
  'armL',
  'armR',
  'wristL',
  'wristR',
  'legL',
  'legR',
  'footL',
  'footR',
]);
const RELATIVE: ReadonlySet<ChannelKey> = new Set([
  'syL',
  'syR',
  'browYL',
  'browYR',
  'mouthCurve',
  'mouthOpen',
]);

function append(
  log: Map<ChannelKey, [number, number][]>,
  channel: ChannelKey,
  at: number,
  value: number
): void {
  const keys = log.get(channel) ?? [];
  keys.push([at, value]);
  log.set(channel, keys);
}

function poseKeys(log: Map<ChannelKey, [number, number][]>, at: number, pose: ScenePose): void {
  const singles: readonly [ChannelKey, number | undefined][] = [
    ['bodyX', pose.x],
    ['bodyY', pose.y],
    ['bodyRoll', pose.roll],
    ['bodySx', pose.shape?.[0]],
    ['bodySy', pose.shape?.[1]],
    ['bodySupport', pose.support],
    ['bodySupportSide', pose.side],
    ['headPitch', pose.pitch],
    ['mouthCurve', pose.face?.[2]],
    ['mouthOpen', pose.face?.[3]],
    ['gazeX', pose.gaze],
    ['hlX', pose.gaze],
    ['massX', pose.gaze === undefined ? undefined : pose.gaze * HEAD_FOLLOW_X_EM + 0],
  ];
  for (const [channel, value] of singles) if (value !== undefined) append(log, channel, at, value);
  const pairs: readonly [
    'arm' | 'wrist' | 'leg' | 'foot' | 'sy' | 'browY' | 'blink',
    Pair | undefined,
  ][] = [
    ['arm', pose.arms],
    ['wrist', pose.wrists],
    ['leg', pose.legs],
    ['foot', pose.feet],
    ['sy', pose.face ? [pose.face[0], pose.face[0] * 0.94] : undefined],
    ['browY', pose.face ? [pose.face[1], pose.face[1] * 0.92] : undefined],
    ['blink', pose.blink === undefined ? undefined : [pose.blink, pose.blink]],
  ];
  for (const [base, pair] of pairs)
    if (pair) {
      append(log, `${base}L`, at, pair[0]);
      append(log, `${base}R`, at, pair[1]);
    }
  if (pose.blinkL !== undefined) append(log, 'blinkL', at, pose.blinkL);
  if (pose.blinkR !== undefined) append(log, 'blinkR', at, pose.blinkR);
}

function flightKeys(
  log: Map<ChannelKey, [number, number][]>,
  phases: readonly ScenePhase[],
  space: BodyMotionSpace
): boolean {
  const flights = phases.filter(([, pose]) => pose.flight);
  if (!flights.length) return false;
  const y = log.get('bodyY') ?? [];
  const supports = log.get('bodySupport') ?? [];
  for (const [at, pose] of flights) {
    const flight = pose.flight!;
    // Ground never moves to make room for a trick. Reduce the entire arc before
    // sampling; clipping samples would flatten the apex in small previews.
    const height = Math.max(0, Math.min(flight.height, -space.minY));
    for (let step = 0; step <= 16; step++) {
      const p = step / 16;
      y.push([at + flight.duration * p, -4 * height * p * (1 - p)]);
    }
    supports.push(
      [Math.max(0, at - 110), 1],
      [at, height > 0 ? 0 : 1],
      [at + flight.duration - 100, height > 0 ? 0 : 1],
      [at + flight.duration, 1]
    );
  }
  log.set('bodyY', y);
  log.set('bodySupport', supports);
  return true;
}

function timeline(keys: Keys, channel: ChannelKey, scene: BodyScene): Keys {
  const rest = RELATIVE.has(channel) ? 0 : CHANNELS[channel].rest;
  const trail = DISTAL_KEYS.has(channel) ? 65 : 0;
  const result: (readonly [number, number])[] = [
    [0, rest],
    ...keys.map(([at, value]) => [at + trail, value] as const),
    [scene.duration - 650, rest],
  ];
  return result.sort((a, b) => a[0] - b[0]);
}

function springFor(channel: ChannelKey, scene: BodyScene, flies: boolean): SpringConfig {
  if (channel === 'bodyY' && flies) return FLIGHT;
  if (DISTAL_KEYS.has(channel)) return DISTAL;
  if (LIMB_KEYS.has(channel)) return LIMB;
  if (channel === 'massX' || channel === 'hlX') return FOLLOW;
  return channel.startsWith('body') ? (scene.spring ?? BODY) : FACE;
}

/** Compile once; frames sample bounded trajectories through the existing springs. */
export function bodySceneTapes(
  scene: BodyScene,
  space: BodyMotionSpace,
  identity?: RigCharacterId
): Tape[] {
  const log = new Map<ChannelKey, [number, number][]>();
  for (const channel of BODY_KEYS) log.set(channel, []);
  for (const channel of LIMB_KEYS) log.set(channel, []);
  for (const [at, pose] of scene.phases)
    poseKeys(log, at, identity ? { ...pose, ...pose.character?.[identity] } : pose);
  const flies = flightKeys(log, scene.phases, space);
  return [...log].map(([channel, keys]) => {
    const bounded = timeline(keys, channel, scene).map(([at, value]) => {
      // A top edge leaves room for grounded anticipation only.
      if (flies && space.minY >= 0 && (channel.startsWith('foot') || channel.startsWith('leg')))
        value = 0;
      if (channel === 'bodyX') value = Math.max(space.minX, Math.min(space.maxX, value));
      if (channel === 'bodyY') value = Math.max(space.minY, Math.min(space.maxY, value));
      return [at, value] as const;
    });
    const tape = (RELATIVE.has(channel) ? relative : absolute)(
      channel,
      bounded,
      scene.duration,
      springFor(channel, scene, flies)
    );
    return {
      ...tape,
      interpolation:
        channel === 'bodyY' && flies
          ? 'linear'
          : channel.startsWith('blink')
            ? undefined
            : 'smooth',
    };
  });
}

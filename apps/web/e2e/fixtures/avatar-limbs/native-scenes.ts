/** Bench-only access to the two actual live rigs; no pose, writer or clock replacement. */
import {
  createEyeRig as createNativeEyeRig,
  type EyeRig,
  type RigOptions,
} from '@/components/eyes/rig/runtime';
import type { SketchName } from '@/components/eyes/rig/sketches';
import { createLifeRandom } from '@/components/eyes/rig/life';

const liveRigs: EyeRig[] = [];
const finishingTake = new URLSearchParams(location.search).get('take') === 'finishing';
const trackedChannels = [
  'mass',
  'bodyRoll',
  'tilt',
  'headYaw',
  'headPitch',
  'bodyX',
  'bodyY',
  'bodySx',
  'bodySy',
  'armL',
  'armR',
  'wristL',
  'wristR',
  'mouthOpen',
  'mouthCurve',
] as const;
type Frame = {
  atMs: number;
  deltaMs: number;
  scene: SketchName | null;
  channels: number[];
};
type FinishingTake = {
  lifeSeed: number;
  trackedChannels: readonly string[];
  frames: Frame[][];
};
const finishing: FinishingTake = { lifeSeed: 0x7a11ce, trackedChannels, frames: [] };

if (finishingTake) Object.defineProperty(window, 'avatarFinishingTake', { value: finishing });

function observeFinishingFrames(rig: EyeRig): void {
  const frames: Frame[] = [];
  finishing.frames.push(frames);
  const step = rig.step.bind(rig);
  rig.step = deltaMs => {
    const awake = step(deltaMs);
    const values = rig.values();
    frames.push({
      atMs: performance.now(),
      deltaMs,
      scene: rig.sketchClock().scene,
      channels: trackedChannels.map(channel => values[channel]),
    });
    return awake;
  };
}

/** The fixture server redirects only useEyesRig's factory import through this seam. */
export function createEyeRig(options: RigOptions = {}): EyeRig {
  const rig = createNativeEyeRig(
    finishingTake && options.lifeRandom
      ? { ...options, lifeRandom: createLifeRandom(finishing.lifeSeed + finishing.frames.length) }
      : options
  );
  if (!options.reducedMotion) {
    if (finishingTake) observeFinishingFrames(rig);
    liveRigs.push(rig);
    if (liveRigs.length > 2) liveRigs.shift();
  }
  return rig;
}

/** Both visible variants keep their production hook's scheduler and lifecycle. */
export function playNativeScene(name: SketchName): void {
  if (liveRigs.length !== 2) throw new Error('The scene bench requires both native live rigs');
  for (const rig of liveRigs) rig.playScene(name);
}

export type { EyeRig } from '@/components/eyes/rig/runtime';

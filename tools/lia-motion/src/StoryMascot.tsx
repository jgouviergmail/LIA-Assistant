import React from 'react';
import { CHANNEL_KEYS, CHANNELS, type ChannelValues } from '../../../apps/web/src/components/eyes/rig/channels';
import { resolvePose } from '../../../apps/web/src/components/eyes/rig/poses';
import type { EyeExpression } from '../../../apps/web/src/components/eyes/expression-engine';
import { NativeStoryPose } from './AvatarShowcase';
import { easeProgress, liftedProgress } from './product-story-timing';
import { mascotDirection, type MascotScreenSide } from './mascot-direction';

export type StoryMascotAct = 'context' | 'clarity' | 'approval' | 'finale';
export type StoryMascotProps = {
  /** Local shot/act time, so the mascot can be reused throughout a long film. */
  frame: number;
  fps: number;
  size: number;
  act: StoryMascotAct;
  /** The product screen's side relative to the mascot, not BIP's stage side. */
  screenSide?: MascotScreenSide;
  previousScreenSide?: MascotScreenSide;
  /** Progress of the carrier's crossing. The eyes lead the head. */
  turnProgress?: number;
  gazeTarget?: readonly [number, number];
  /** Optional local times for brief, smiling looks at the audience. */
  audienceGlances?: readonly number[];
  lookAtAudience?: boolean;
};

const poses: Record<StoryMascotAct, { from: EyeExpression; to: EyeExpression; gaze: readonly [number, number] }> = {
  context: { from: 'neutral', to: 'attentive', gaze: [0.36, -0.12] },
  clarity: { from: 'attentive', to: 'thinking', gaze: [0.46, -0.20] },
  approval: { from: 'thinking', to: 'attentive', gaze: [0.40, -0.02] },
  finale: { from: 'attentive', to: 'joy', gaze: [-0.16, -0.02] },
};

/** Authored gaze and small gestures project native expression recipes.
 * Breathing is anchored at the feet; there is no floating loop or speech tape. */
export function StoryMascot({ frame, fps, size, act, screenSide = 'right', previousScreenSide, turnProgress = 1, gazeTarget, audienceGlances, lookAtAudience = false }: StoryMascotProps) {
  const seconds = Math.max(0, Math.floor(frame)) / fps;
  const recipe = poses[act];
  const from = resolvePose(recipe.from, 'billes');
  const to = resolvePose(recipe.to, 'billes');
  const transition = easeProgress(seconds, 0, 0.55);
  const values = { ...from } as ChannelValues;
  for (const channel of CHANNEL_KEYS) values[channel] = from[channel] + (to[channel] - from[channel]) * transition;

  const moments = audienceGlances ?? (act === 'approval' ? [5.9] : act === 'finale' ? [0.7] : []);
  const audience = lookAtAudience ? easeProgress(seconds, 0.08, 0.52) : moments.reduce((weight, at) => Math.max(weight, liftedProgress(seconds, at, at + 1.1, 0.4)), 0);
  const smile = resolvePose('joy', 'billes');
  // A smile is a real native pose, briefly blended into the held screen gaze.
  for (const channel of CHANNEL_KEYS) {
    if (['gaze', 'aura', 'mass'].includes(CHANNELS[channel].group)) continue;
    values[channel] += (smile[channel] - values[channel]) * audience * 0.72;
  }
  const direction = mascotDirection({ screenSide, previousScreenSide, turnProgress, gazeTarget: gazeTarget ?? [screenSide === 'left' ? -0.78 : 0.78, recipe.gaze[1]], audienceWeight: audience });
  Object.assign(values, direction);
  const lean = liftedProgress(seconds, 0.38, 2.85, 0.6);
  const nod = liftedProgress(seconds, 1.15, 1.9, 0.28);
  values.tilt = Math.max(-4, Math.min(4, values.tilt + direction.gazeX * 3.8 * lean - 1.4 * audience));
  values.headPitch += (act === 'approval' || act === 'finale' ? 0.14 : 0.06) * nod;
  values.mass = 1 + Math.sin(seconds * 1.45) * 0.0055;
  values.massY = 0;
  const blinkTime = seconds % 20;
  const blink = [1.72, 5.16, 9.22, 13.18, 17.64].reduce((amount, at) => Math.max(amount, liftedProgress(blinkTime, at, at + 0.08, 0.07)), 0);
  values.blinkL = blink;
  values.blinkR = blink;
  values.mouthArc = Math.abs(values.mouthCurve);

  return <div style={{ position: 'relative', width: size, height: size }} aria-hidden="true">
    <div style={{ position: 'absolute', left: size * 0.14, top: size * 0.88, width: size * 0.72, height: size * 0.065, borderRadius: '50%', background: 'radial-gradient(ellipse,rgba(20,62,82,.16),transparent 72%)', filter: `blur(${size * 0.016}px)`, transform: `scaleX(${1 + (values.mass - 1) * 3})` }} />
    <NativeStoryPose size={size} values={values} />
  </div>;
}

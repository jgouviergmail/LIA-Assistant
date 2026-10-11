/** The compact, slightly open resting smile keeps the native acting channels. */
import type { ChannelValues } from '../rig/channels';
import { finite } from './sphere-geometry';

function unit(value: number): number {
  return Math.max(0, Math.min(1, finite(value)));
}

/** Release the resting anatomy as the signed expression leaves the calm smile. */
export function smileyRestInfluence(values: Readonly<ChannelValues>): number {
  const curve = finite(values.mouthCurve);
  const release = Math.max(unit((curve - 0.4) / 0.16), unit((0.32 - curve) / 0.2));
  const eased = release * release * (3 - 2 * release);
  const opening = unit(values.mouthOpen / 0.56);
  const articulated = opening * opening * (3 - 2 * opening);
  return (1 - eased) * (1 - articulated);
}

export function smileyMouthWidth(values: Readonly<ChannelValues>): number {
  const release = Math.max(
    unit(values.mouthOpen / 0.16),
    unit((values.mouthCurve - 0.4) / 0.16),
    unit((0.32 - values.mouthCurve) / 0.12)
  );
  const eased = release * release * (3 - 2 * release);
  // The chosen preview spans .84em inside the existing 1.45em native mouth.
  const restRatio = 0.84 / (1.45 * 0.72);
  return finite(values.mouthW) * (restRatio + (1 - restRatio) * eased);
}

/** The compact, slightly open resting smile keeps the native acting channels. */
import type { ChannelValues } from './channels';
const finite = (value: number) => (Number.isFinite(value) ? value : 0);

function unit(value: number): number {
  return Math.max(0, Math.min(1, finite(value)));
}

/** Release the resting anatomy as the signed expression leaves the calm smile. */
export function sculptedRestInfluence(values: Readonly<ChannelValues>): number {
  const curve = finite(values.mouthCurve);
  const release = Math.max(unit((curve - 0.4) / 0.16), unit((0.32 - curve) / 0.2));
  const eased = release * release * (3 - 2 * release);
  const opening = unit(values.mouthOpen / 0.56);
  const articulated = opening * opening * (3 - 2 * opening);
  return (1 - eased) * (1 - articulated);
}

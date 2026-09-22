/** Fixed-topology contours for the line and ring skins. */
import type { ChannelKey, ChannelValues, EyeSide } from './channels';

export const STROKE_CHANNELS: readonly ChannelKey[] = [
  'strokeArcL',
  'strokeArcR',
  'strokeRoundL',
  'strokeRoundR',
  'strokeHorizontalL',
  'strokeHorizontalR',
  'strokeWeightL',
  'strokeWeightR',
];

const unit = (n: number) => (Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0);
const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const VERTICAL = [50, 16, 50, 38, 50, 62, 50, 84];
const HORIZONTAL = [12, 50, 35, 50, 65, 50, 88, 50];
const RING = [10, 50, 10, -3, 90, -3, 90, 50];

export function strokeContours(v: Readonly<ChannelValues>, side: EyeSide) {
  const arc = Math.max(-1, Math.min(1, v[`strokeArc${side}`] || 0));
  const round = unit(v[`strokeRound${side}`]);
  const horizontal = unit(v[`strokeHorizontal${side}`]);
  const bend = arc >= 0 ? [10, 65, 20, 10, 80, 10, 90, 65] : [10, 35, 20, 90, 80, 90, 90, 35];
  const points = VERTICAL.map((n, i) =>
    mix(mix(mix(n, HORIZONTAL[i], horizontal), RING[i], round), bend[i], Math.abs(arc))
  ).map(n => Math.round(n * 1000) / 1000);
  return {
    upper: `M ${points[0]} ${points[1]} C ${points.slice(2).join(' ')}`,
    lower: 'M 90 50 C 90 103 10 103 10 50',
    lowerOpacity: round * (1 - Math.abs(arc)),
    width: Math.max(8, Math.min(36, v[`strokeWeight${side}`] || 16)),
  };
}

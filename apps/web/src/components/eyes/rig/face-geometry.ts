/** Continuous facial contours. Geometry only: no clock, spring or DOM reads. */
import { STROKE_CHANNELS } from './stroke-geometry';
import type { ChannelKey, ChannelValues, EyeSide } from './channels';
export { sculptedMouthContours, type SculptedMouthContours } from './sculpted-mouth';

/** Channels read by the SVG projection, also checked by the boundary guard. */
export const SVG_CHANNELS: readonly ChannelKey[] = [
  ...STROKE_CHANNELS,
  'mouthCurve',
  'mouthArc',
  'mouthOpen',
  'mouthSkew',
  'browArcL',
  'browArcR',
  'browRotL',
  'browRotR',
  'browSL',
  'browSR',
];

function bounded(value: number, min: number, max: number): number {
  return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : 0;
}

function n(value: number): string {
  return String(Math.round(value * 1000) / 1000 || 0);
}

/** A filled ribbon whose two lips never exchange sides at a signed crossing. */
export function mouthPath(v: Readonly<ChannelValues>): string {
  const curve = bounded(v.mouthCurve, -1, 1);
  const arc = bounded(v.mouthArc, 0, 1);
  const skew = bounded(v.mouthSkew, -1, 1) * 7;
  const upper = 32 + curve * 22 - arc * arc * 9;
  const closedDepth = 6 + arc * arc * 32;
  const lower = upper + closedDepth + bounded(v.mouthOpen, 0, 1) * (80 - upper - closedDepth);
  return `M 5 ${n(32 - skew)} C 27 ${n(upper - skew)} 73 ${n(upper + skew)} 95 ${n(32 + skew)} Q 99 ${n(34 + skew)} 95 ${n(36 + skew)} C 73 ${n(lower + skew)} 27 ${n(lower - skew)} 5 ${n(36 - skew)} Q 1 ${n(34 - skew)} 5 ${n(32 - skew)} Z`;
}

/** Inner/outer ends articulate around a curved centre, preserving stroke weight. */
export function browPath(v: Readonly<ChannelValues>, side: EyeSide): string {
  const arc = bounded(v[`browArc${side}`], 0, 1);
  const tilt = bounded(v[`browRot${side}`], -30, 30) * 0.5;
  return `M 7 ${n(22 - tilt)} C 29 ${n(22 - arc * 30 - tilt * 0.35)} 71 ${n(22 - arc * 30 + tilt * 0.35)} 93 ${n(22 + tilt)}`;
}

/** A full tapered cartoon brow, driven by the same continuous arch and tilt. */
export function sculptedBrowPath(v: Readonly<ChannelValues>, side: EyeSide): string {
  const mirrored = side === 'R';
  const arc = bounded(v[`browArc${side}`], 0, 1);
  const tilt = bounded(v[`browRot${side}`], -30, 30) * 0.65 * (mirrored ? -1 : 1);
  const upper = 17 - arc * 25;
  const weight = bounded(v[`browS${side}`], 0.94, 1.06);
  const lower = upper + 20 * weight;
  const point = (x: number, y: number) => `${mirrored ? 100 - x : x} ${n(y)}`;
  return `M ${point(5, 22 - tilt)} C ${point(24, upper - tilt * 0.35)} ${point(68, upper + tilt * 0.35)} ${point(94, 22 + tilt)} Q ${point(99, 26 + tilt)} ${point(94, 22 + 9 * weight + tilt)} C ${point(70, lower + tilt * 0.35)} ${point(27, lower - tilt * 0.35)} ${point(8, 22 + 12 * weight - tilt)} Q ${point(1, 22 + 8 * weight - tilt)} ${point(5, 22 - tilt)} Z`;
}

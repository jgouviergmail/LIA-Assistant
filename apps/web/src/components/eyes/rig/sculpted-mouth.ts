/** Smiley-only continuous mouth anatomy. The native rig still owns all acting. */
import type { ChannelValues } from './channels';
import { smileyRestInfluence } from '../smiley/rest-mouth';

export interface SculptedMouthContours {
  cavity: string;
  teeth: string;
  tongue: string;
}

function bounded(value: number, min: number, max: number): number {
  return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : 0;
}

function n(value: number): string {
  return String(Math.round(value * 1000) / 1000 || 0);
}

interface LipProfile {
  left: number;
  right: number;
  corner: number;
  upper: number;
  lower: number;
  edgeDepth: number;
  skew: number;
}

/** Shared upper edge: teeth follow the lip rather than exposing a straight bar. */
function ribbon(p: LipProfile): string {
  const controlLeft = p.left + (p.right - p.left) * 0.27;
  const controlRight = p.right - (p.right - p.left) * 0.27;
  return `M ${n(p.left)} ${n(p.corner - p.skew)} C ${n(controlLeft)} ${n(p.upper - p.skew)} ${n(controlRight)} ${n(p.upper + p.skew)} ${n(p.right)} ${n(p.corner + p.skew)} Q ${n(p.right + 3)} ${n(p.corner + p.edgeDepth * 0.5 + p.skew)} ${n(p.right)} ${n(p.corner + p.edgeDepth + p.skew)} C ${n(controlRight)} ${n(p.lower + p.skew)} ${n(controlLeft)} ${n(p.lower - p.skew)} ${n(p.left)} ${n(p.corner + p.edgeDepth - p.skew)} Q ${n(p.left - 3)} ${n(p.corner + p.edgeDepth * 0.5 - p.skew)} ${n(p.left)} ${n(p.corner - p.skew)} Z`;
}

/** The approved resting cavity and its short, curved ivory tooth ribbon. */
const REST_CAVITY = [
  10, 29, 28, 32, 72, 32, 90, 29, 92, 29, 89, 33, 80, 42, 65, 47, 50, 47, 35, 47, 20, 42, 11, 33, 8,
  29, 10, 29,
];
const REST_TEETH = [
  26, 31, 38, 33, 62, 33, 74, 31, 73.5, 33.5, 73, 36, 66, 37, 58, 37.5, 50, 37.5, 42, 37.5, 34, 37,
  27, 36, 26.5, 33.5, 26, 31,
];

/** Split the native lower cubic exactly in half to match the resting topology. */
function ribbonPoints(p: LipProfile): number[] {
  const a = p.left + (p.right - p.left) * 0.27;
  const b = p.right - (p.right - p.left) * 0.27;
  const edge = p.corner + p.edgeDepth;
  const mid = (edge + 3 * p.lower) / 4;
  return [
    p.left,
    p.corner - p.skew,
    a,
    p.upper - p.skew,
    b,
    p.upper + p.skew,
    p.right,
    p.corner + p.skew,
    p.right + 3,
    p.corner + p.edgeDepth * 0.5 + p.skew,
    p.right,
    edge + p.skew,
    (p.right + b) / 2,
    (edge + p.lower) / 2 + p.skew,
    (p.right + 2 * b + a) / 4,
    mid + p.skew * 0.5,
    50,
    mid,
    (b + 2 * a + p.left) / 4,
    mid - p.skew * 0.5,
    (a + p.left) / 2,
    (edge + p.lower) / 2 - p.skew,
    p.left,
    edge - p.skew,
    p.left - 3,
    p.corner + p.edgeDepth * 0.5 - p.skew,
    p.left,
    p.corner - p.skew,
  ];
}

function restingRibbon(
  current: LipProfile,
  closed: LipProfile,
  rest: readonly number[],
  influence: number
): string {
  const base = ribbonPoints(closed);
  const drawing = ribbonPoints(current).map((value, index) =>
    n(value + (rest[index] - base[index]) * influence)
  );
  const pair = (index: number) => `${drawing[index]} ${drawing[index + 1]}`;
  return `M ${pair(0)} C ${pair(2)} ${pair(4)} ${pair(6)} Q ${pair(8)} ${pair(10)} C ${pair(12)} ${pair(14)} ${pair(16)} C ${pair(18)} ${pair(20)} ${pair(22)} Q ${pair(24)} ${pair(26)} Z`;
}

function tonguePath(profile: LipProfile, open: number): string {
  const rx = 19 * open;
  const ry = 7 * open;
  const floor = (profile.corner + profile.edgeDepth) * 0.25 + profile.lower * 0.75;
  const cy = floor - ry * 0.15;
  // Four cubic quarters are an ellipse; the cavity clips its lower edge.
  const k = 0.552285;
  return `M ${n(50 - rx)} ${n(cy)} C ${n(50 - rx)} ${n(cy - ry * k)} ${n(50 - rx * k)} ${n(cy - ry)} 50 ${n(cy - ry)} C ${n(50 + rx * k)} ${n(cy - ry)} ${n(50 + rx)} ${n(cy - ry * k)} ${n(50 + rx)} ${n(cy)} C ${n(50 + rx)} ${n(cy + ry * k)} ${n(50 + rx * k)} ${n(cy + ry)} 50 ${n(cy + ry)} C ${n(50 - rx * k)} ${n(cy + ry)} ${n(50 - rx)} ${n(cy + ry * k)} ${n(50 - rx)} ${n(cy)} Z`;
}

function lipProfile(curve: number, open: number, skew: number): LipProfile {
  const smile = Math.max(0, curve);
  const bowl = bounded((smile - 0.4) / 0.6, 0, 1);
  const corner = 32 - smile * 10;
  const restUpper = corner + curve * 13 - open * 4;
  const closedDepth = 3 + smile * smile * 27;
  const closedLower = Math.min(72 + bowl, restUpper + closedDepth + 20 * bowl * bowl);
  const jawFloor = 72 + 6 * bowl;
  // Speech rounds O/OU; the smooth .4-to-.6 release leaves the approved grin intact.
  const speech = bounded((0.6 - smile) / 0.2, 0, 1);
  const purse = open * speech * speech * (3 - 2 * speech);
  const upper = Math.max(5, restUpper - purse * 12);
  const lower = closedLower + open * (jawFloor - closedLower);
  const left = Math.min(34, 7 + open * 8 * (1 - smile) + purse * 25);
  return {
    left,
    right: 100 - left,
    corner,
    upper,
    lower,
    edgeDepth: 3 + open * 19,
    skew: skew * Math.min(5, upper, 80 - lower),
  };
}

function toothProfile(profile: LipProfile, curve: number, open: number): LipProfile {
  const smile = Math.max(0, curve);
  const reveal = bounded((Math.max(smile, open) - 0.2) / 0.6, 0, 1);
  const toothDepth = Math.min(9, (profile.lower - profile.upper) * 0.35) * reveal;
  return {
    ...profile,
    corner: profile.corner + 1.6,
    upper: profile.upper + 1.6,
    lower: profile.upper + 1.6 + toothDepth,
    edgeDepth: toothDepth * 0.7,
  };
}

/** Rest anatomy fades on native channels; opening remains continuous and monotone. */
export function sculptedMouthContours(values: Readonly<ChannelValues>): SculptedMouthContours {
  const curve = bounded(values.mouthCurve, -1, 1);
  const open = bounded(values.mouthOpen, 0, 1);
  const skew = bounded(values.mouthSkew, -1, 1);
  const profile = lipProfile(curve, open, skew);
  const teeth = toothProfile(profile, curve, open);
  const influence = smileyRestInfluence(values);
  // A symmetric baseline leaves the native mouth skew intact in the drawing.
  const closed = influence ? lipProfile(curve, 0, 0) : profile;
  const bowl = bounded((curve - 0.4) / 0.6, 0, 1);
  return {
    // Offset the closed native anatomy, rather than shrinking B into an older
    // narrow seam at the start of speech. Full smiles and signed frowns stay native.
    cavity: influence ? restingRibbon(profile, closed, REST_CAVITY, influence) : ribbon(profile),
    teeth: influence
      ? restingRibbon(teeth, toothProfile(closed, curve, 0), REST_TEETH, influence)
      : ribbon(teeth),
    tongue: tonguePath(profile, Math.max(open, bowl * 0.65)),
  };
}

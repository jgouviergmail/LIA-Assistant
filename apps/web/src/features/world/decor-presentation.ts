/** Finite, authored local appearance. Never a private screen or external content. */
import type { WorldProp } from './types';

export type ScreenVariant = 0 | 1 | 2 | 3 | 4;
export interface DecorPresentation {
  readonly light?: boolean;
  readonly screen?: ScreenVariant;
  readonly machine?: number;
  readonly press?: number;
  readonly barReach?: number;
}
export type PersonInteraction =
  | { kind: 'coin'; phase: number }
  | { kind: 'press'; lift: number; reach: number }
  | { kind: 'fish'; phase: number };
export const NO_DECOR: DecorPresentation = Object.freeze({});
export const FOUNTAIN_IMPACT = 0.52;
export const FISHING_IMPACT = 0.34;
export const WORKOUT_CUES = [0.16, 0.41, 0.66] as const;
export const WORKOUT_BODY_Y = 1.45;
export const BAR_RACK_Y = 0.4;
export const BAR_CHEST_Y = 1.55;
export const BAR_HEIGHT = 1.55;
export const BAR_LIFT = 0.45;
/** The one rule for a prop whose authored screen cycles illustrations; the sage desk is a plain table. */
export function hasDecorScreen(prop: Pick<WorldProp, 'kind' | 'tone'>): boolean {
  return prop.kind === 'display' || (prop.kind === 'desk' && prop.tone !== 'sage');
}
export function pressReach(phase: number): number {
  const progress = phase < 0.14 ? phase / 0.14 : phase < 0.91 ? 1 : Math.max(0, (1 - phase) / 0.09);
  return progress * progress * (3 - 2 * progress);
}
/** Where the rigid bar sits for a presentation: racked, then over the chest, then pressed. */
export function barPosition(decor: DecorPresentation): { y: number; z: number } {
  const reach = decor.barReach ?? (decor.press === undefined ? 0 : 1);
  return {
    y: BAR_RACK_Y + (BAR_CHEST_Y - BAR_RACK_Y) * reach,
    z: BAR_HEIGHT + (decor.press ?? 0) * BAR_LIFT,
  };
}
const NEXT: Record<ScreenVariant, ScreenVariant> = { 0: 1, 1: 2, 2: 3, 3: 4, 4: 0 };
export function nextScreen(value: ScreenVariant): ScreenVariant {
  return NEXT[value];
}
export function pressLift(phase: number): number {
  if (phase <= 0.16 || phase >= 0.91) return 0;
  return Math.sin((((phase - 0.16) / 0.25) % 1) * Math.PI);
}
export function decorSignature(value: DecorPresentation): string {
  return [
    value.light === undefined ? 'auto' : value.light ? 'on' : 'off',
    value.screen ?? 0,
    value.machine ?? '',
    value.press ?? '',
    value.barReach ?? '',
  ].join(':');
}
/** Most props present nothing: their per-frame key reuses one precomputed signature. */
export const NO_DECOR_SIGNATURE = decorSignature(NO_DECOR);

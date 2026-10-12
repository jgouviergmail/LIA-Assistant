/** Stage direction for the native face. Positive X points to screen-right.
 * A crossing preserves the old target until the eyes lead the slower head. */
export type MascotScreenSide = 'left' | 'right';

export type MascotDirection = {
  screenSide?: MascotScreenSide;
  previousScreenSide?: MascotScreenSide;
  turnProgress?: number;
  gazeTarget?: readonly [number, number];
  audienceWeight?: number;
};

const clamp = (value: number) => Math.max(0, Math.min(1, value));
const smooth = (value: number) => {
  const t = clamp(value);
  return t * t * (3 - 2 * t);
};
const sideX = (side: MascotScreenSide) => side === 'left' ? -0.78 : 0.78;

export function mascotDirection({
  screenSide = 'right',
  previousScreenSide = screenSide,
  turnProgress = 1,
  gazeTarget,
  audienceWeight = 0,
}: MascotDirection) {
  const to = gazeTarget?.[0] ?? sideX(screenSide);
  const from = previousScreenSide === screenSide ? to : sideX(previousScreenSide);
  const eyes = smooth(turnProgress / 0.65);
  const head = smooth((turnProgress - 0.12) / 0.88);
  const audience = clamp(audienceWeight);
  const gazeX = audience === 1 ? 0 : (from + (to - from) * eyes) * (1 - audience);
  const gazeY = audience === 1 ? 0 : (gazeTarget?.[1] ?? -0.12) * (1 - audience);
  return {
    gazeX,
    gazeY,
    // Native headYaw is a normalized turn; its renderer projects ±16 degrees.
    headYaw: audience === 1 ? 0 : Math.max(-1, Math.min(1, (from + (to - from) * head) * 1.2)) * (1 - audience),
    headPitch: gazeY * 0.35,
  };
}

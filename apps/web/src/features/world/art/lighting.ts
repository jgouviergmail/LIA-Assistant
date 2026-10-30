import type { Atmosphere } from '../atmosphere';
import type { Sprite } from './painter';

/** One bounded ambient level per phase; no viewport- or actor-dependent lighting. */
export function nightStrength(phase: Atmosphere['phase']): number {
  if (phase === 'night') return 0.6;
  if (phase === 'evening') return 0.3;
  if (phase === 'dawn') return 0.18;
  return 0;
}
/** Gentle interior dusk keeps furniture legible while warm fixtures stand out. */
export function ambientStrength(phase: Atmosphere['phase'], indoors: boolean): number {
  return nightStrength(phase) * (indoors ? 0.3 : 1);
}
export function nightColour(strength: number, phase: Atmosphere['phase'] = 'night'): string {
  const colour = phase === 'dawn' ? '158,119,87' : phase === 'evening' ? '93,72,86' : '24,37,60';
  return `rgba(${colour},${strength})`;
}
/** Bake once per cached outdoor sprite. source-atop preserves its exact alpha mask. */
export function shadeSprite(
  sprite: Sprite,
  strength: number,
  phase: Atmosphere['phase'] = 'night'
): Sprite {
  if (!strength) return sprite;
  const c = sprite.canvas.getContext('2d');
  if (!c) throw new Error('Canvas unavailable');
  c.save();
  c.setTransform(1, 0, 0, 1, 0, 0);
  c.globalCompositeOperation = 'source-atop';
  c.fillStyle = nightColour(strength, phase);
  c.fillRect(0, 0, sprite.canvas.width, sprite.canvas.height);
  c.restore();
  return sprite;
}

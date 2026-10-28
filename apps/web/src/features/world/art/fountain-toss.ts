import type { CosmeticFrame } from '../cosmetic-effects';
import { FOUNTAIN_IMPACT } from '../decor-presentation';
import { project } from '../geometry';
import type { Point } from '../types';

/** Under reduced motion the impact is one still ring set, held until the beat ends. */
const STILL_RIPPLE = 0.5;

/** One ballistic flight, followed by one impact; never a looping floating coin. */
export function fountainToss(beat: CosmeticFrame): { coin: Point | null; ripple: number } {
  const phase = beat.phase;
  const ripple = Math.max(0, (phase - FOUNTAIN_IMPACT) / (1 - FOUNTAIN_IMPACT));
  if (!beat.origin || phase < 0.18 || phase >= FOUNTAIN_IMPACT) return { coin: null, ripple };
  const progress = (phase - 0.18) / (FOUNTAIN_IMPACT - 0.18);
  const from = beat.origin,
    to = beat.point;
  const ground = { x: from.x + (to.x - from.x) * progress, y: from.y + (to.y - from.y) * progress };
  const height =
    1.2 * (1 - progress) + beat.elevation * progress + Math.sin(progress * Math.PI) * 1.7;
  return { coin: project(ground, height), ripple };
}
export function paintFountainToss(
  c: CanvasRenderingContext2D,
  beat: CosmeticFrame,
  reduced: boolean
): void {
  const { coin, ripple } = fountainToss(beat),
    at = project(beat.point, beat.elevation);
  c.save();
  if (coin && !reduced) {
    c.fillStyle = '#f4cf65';
    c.strokeStyle = '#af782f';
    c.lineWidth = 1;
    c.beginPath();
    c.ellipse(
      coin.x,
      coin.y,
      2 + Math.abs(Math.cos(beat.phase * 40)) * 1.5,
      3.5,
      -0.4,
      0,
      Math.PI * 2
    );
    c.fill();
    c.stroke();
  }
  if (ripple > 0) {
    const spread = reduced ? STILL_RIPPLE : ripple;
    c.strokeStyle = '#e0fff5';
    c.lineWidth = 1.4;
    c.globalAlpha = (1 - spread) * 0.9;
    for (let i = 0; i < 3; i++) {
      const radius = 3 + spread * (24 - i * 6);
      c.beginPath();
      c.ellipse(at.x, at.y, radius, radius / 2, 0, 0, Math.PI * 2);
      c.stroke();
    }
    if (!reduced && ripple < 0.35) {
      for (let i = 0; i < 5; i++) {
        const angle = i * Math.PI * 0.4,
          x = at.x + Math.cos(angle) * ripple * 35,
          y = at.y - Math.sin((ripple / 0.35) * Math.PI) * 11 + Math.sin(angle) * ripple * 12;
        c.fillStyle = '#dcf9ef';
        c.beginPath();
        c.ellipse(x, y, 1.2, 2, angle, 0, Math.PI * 2);
        c.fill();
      }
    }
  }
  c.restore();
}

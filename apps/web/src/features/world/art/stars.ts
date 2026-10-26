import type { Atmosphere } from '../atmosphere';
import type { Camera, Quality } from '../types';
import { nightStrength } from './lighting';

// A fixed sky, painted behind the opaque plateau. No RNG, timers or per-frame allocation.
const STARS = Array.from({ length: 180 }, (_, i) => ({
  x: ((i * 754877 + 19391) % 1000000) / 1000000,
  y: ((i * 569841 + 73127) % 1000000) / 1000000,
  radius: [0.55, 0.75, 1, 0.65, 1.35][i % 5],
  bright: i % 13 === 0,
}));
export function paintStars(
  c: CanvasRenderingContext2D,
  camera: Camera,
  phase: Atmosphere['phase'],
  quality: Quality
): void {
  const strength = nightStrength(phase);
  if (!strength) return;
  c.save();
  c.globalAlpha = Math.min(1, strength * 1.5);
  const count = { low: 80, balanced: 130, high: 180 }[quality];
  for (let i = 0; i < count; i++) {
    const star = STARS[i],
      x = star.x * camera.width,
      y = star.y * camera.height;
    c.fillStyle = star.bright ? '#fff0cf' : '#93b6d9';
    c.beginPath();
    c.arc(x, y, star.radius, 0, Math.PI * 2);
    c.fill();
    if (star.bright) {
      c.globalAlpha = strength * 0.45;
      c.fillRect(x - 3, y - 0.45, 6, 0.9);
      c.fillRect(x - 0.45, y - 3, 0.9, 6);
      c.globalAlpha = Math.min(1, strength * 1.5);
    }
  }
  c.restore();
}

import { project } from '../geometry';
import type { WorldProp } from '../types';

/** Two falling petals per visible blossom tree. No emitter, retained particles or timers. */
export function paintGardenMotion(
  c: CanvasRenderingContext2D,
  prop: WorldProp,
  time: number
): void {
  if (prop.kind !== 'tree' || prop.tone !== 'clay') return;
  c.save();
  c.fillStyle = '#f4b0ce';
  for (let i = 0; i < 2; i++) {
    const phase = (time * 0.13 + prop.x * 0.17 + prop.y * 0.11 + i * 0.5) % 1;
    const at = project(
      { x: prop.x + 0.5 + Math.sin(phase * 7 + i) * 0.3, y: prop.y + 0.5 + phase * 0.8 },
      2.6 * (1 - phase)
    );
    c.globalAlpha = Math.min(1, phase * 8, (1 - phase) * 5) * 0.8;
    c.beginPath();
    c.ellipse(at.x, at.y, 2.2, 1, Math.sin(time + i), 0, Math.PI * 2);
    c.fill();
  }
  c.restore();
}
export function paintScreenMotion(
  c: CanvasRenderingContext2D,
  prop: WorldProp,
  time: number
): void {
  if (prop.kind !== 'desk' || prop.tone === 'sage') return;
  const at = project({ x: prop.x + 0.77 + (prop.width - 1.2) / 2, y: prop.y + 0.24 }, 1.2);
  c.save();
  c.globalAlpha = 0.35 + Math.sin(time * 1.5) * 0.15;
  c.strokeStyle = '#e2fff2';
  c.lineWidth = 1.2;
  c.beginPath();
  c.moveTo(at.x, at.y);
  c.lineTo(at.x, at.y - 3);
  c.stroke();
  c.restore();
}

import { nightStrength } from './lighting';
import { paintPondLife } from './pond';
import { paintRoomMotion } from './room-motion';
import type { Atmosphere } from '../atmosphere';
import { paintGardenMotion, paintScreenMotion } from './garden-motion';
/** Tiny local decorative loops. No timers, network, user data or per-frame textures. */
import { project } from '../geometry';
import type { WorldProp } from '../types';
export function paintObjectMotion(
  c: CanvasRenderingContext2D,
  prop: WorldProp,
  time: number,
  reduced: boolean,
  atmosphere?: Atmosphere
): void {
  paintRoomMotion(c, prop, time, reduced, atmosphere);
  if (!reduced) {
    if (prop.kind === 'pond')
      paintPondLife(c, prop, time, atmosphere ? nightStrength(atmosphere.phase) : 0);
    paintGardenMotion(c, prop, time);
    paintScreenMotion(c, prop, time);
  }
  if (prop.kind !== 'fountain') return;
  const at = (x: number, y: number, z: number) => project({ x: prop.x + x, y: prop.y + y }, z);
  c.save();
  c.lineCap = 'round';
  const phase = reduced ? 0.35 : time;
  for (let i = 0; i < 8; i++) {
    const angle = (i * Math.PI) / 4;
    const a = at(1.5, 1.5, 1.03),
      b = at(1.5 + Math.cos(angle) * 0.37, 1.5 + Math.sin(angle) * 0.37, 1.72);
    const end = at(1.5 + Math.cos(angle) * 0.85, 1.5 + Math.sin(angle) * 0.85, 0.28);
    c.beginPath();
    c.moveTo(a.x, a.y);
    c.quadraticCurveTo(b.x, b.y, end.x, end.y);
    c.strokeStyle = 'rgba(211,241,226,.57)';
    c.lineWidth = 1.3;
    c.stroke();
    const t = (phase * 0.85 + i * 0.137) % 1;
    const x = (1 - t) * (1 - t) * a.x + 2 * (1 - t) * t * b.x + t * t * end.x;
    const y = (1 - t) * (1 - t) * a.y + 2 * (1 - t) * t * b.y + t * t * end.y;
    c.fillStyle = '#edf7e6';
    c.beginPath();
    c.arc(x, y, 1.3, 0, Math.PI * 2);
    c.fill();
  }
  c.restore();
}

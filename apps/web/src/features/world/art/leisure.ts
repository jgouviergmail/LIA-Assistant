import type { Painter } from './painter';
import type { WorldProp } from '../types';
import { tube } from './solid';
import { project } from '../geometry';
export function paintHerbarium(p: Painter, o: WorldProp): void {
  const timber = '#9b7951',
    d = 0.8;
  for (const x of [0.05, o.width - 0.17])
    for (const y of [0.08, d - 0.2]) p.box(x, y, 0, 0.12, 0.12, 2.16, timber);
  for (const z of [0.45, 1.22]) {
    p.box(0, 0.08, z, o.width, 0.12, 0.08, timber);
    p.box(0, d - 0.14, z, o.width, 0.12, 0.08, timber);
    for (let i = 0; i < 4; i++) {
      const x = 0.25 + i * 0.66;
      p.box(x, 0.25, z + 0.08, 0.4, 0.4, 0.28, ['#ad6e4d', '#c09b70'][i % 2]);
      p.surface(x + 0.03, 0.28, z + 0.365, 0.34, 0.34, '#5c5141');
      p.box(x + 0.09, 0.33, z + 0.37, 0.2, 0.24, 0.23, '#5e8e69');
      p.box(x + 0.02, 0.38, z + 0.44, 0.34, 0.15, 0.12, '#87a675');
      p.box(x + 0.13, 0.36, z + 0.6, 0.11, 0.13, 0.16, i % 2 ? '#b29b55' : '#aac684');
      p.panel(x + 0.12, 0.655, z + 0.14, 0.15, 0.09, '#eadac0');
    }
  }
  p.box(0, 0, 2.12, o.width, 0.12, 0.12, timber);
  p.box(0, d - 0.12, 2.12, o.width, 0.12, 0.12, timber);
}
export function paintRadio(p: Painter, o: WorldProp): void {
  p.box(0.14, 0.08, 0, o.width - 0.28, o.depth - 0.16, 0.24, '#344f4d');
  p.box(0, 0, 0.24, o.width, o.depth, 1.18, '#9d6b46');
  p.panel(0.1, o.depth + 0.005, 0.35, o.width - 0.2, 0.95, '#614d3c');
  for (const x of [0.47, o.width - 0.47]) {
    const at = project({ x, y: o.depth + 0.01 }, 0.84);
    p.ctx.save();
    p.ctx.translate(at.x, at.y);
    p.ctx.transform(1, 0.5, 0, -1, 0, 0);
    p.ctx.fillStyle = '#273e3f';
    p.ctx.beginPath();
    p.ctx.arc(0, 0, 10, 0, Math.PI * 2);
    p.ctx.fill();
    p.ctx.strokeStyle = '#be9a65';
    p.ctx.lineWidth = 1;
    for (let y = -7; y <= 7; y += 3) {
      p.ctx.beginPath();
      p.ctx.moveTo(-6, y);
      p.ctx.lineTo(6, y);
      p.ctx.stroke();
    }
    p.ctx.restore();
  }
  p.panel(0.95, o.depth + 0.02, 0.96, o.width - 1.9, 0.26, '#abd0be');
  for (let x = 1.02; x < o.width - 0.98; x += 0.13)
    p.panel(x, o.depth + 0.025, 1.02, 0.018, 0.1, '#3e716c');
  for (const x of [1.08, o.width - 1.08])
    p.box(x, o.depth - 0.04, 0.53, 0.16, 0.13, 0.16, '#c4a66e');
  p.box(0.08, 0.08, 1.42, o.width - 0.16, o.depth - 0.16, 0.06, '#c4a076');
  tube(
    p,
    { x: o.width - 0.3, y: 0.2, z: 1.48 },
    { x: o.width - 0.6, y: 0.2, z: 1.88 },
    0.015,
    '#b5c3b4',
    6
  );
}

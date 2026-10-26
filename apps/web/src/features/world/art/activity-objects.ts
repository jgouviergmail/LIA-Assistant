/** Distinct silhouettes for activities: semantics are authored, never inferred from user data. */
import type { Painter } from './painter';
import type { WorldProp } from '../types';
import { project } from '../geometry';
import { tube } from './solid';
import { paintTable, paintDesk } from './interiors';
const ink = '#304f51',
  oak = '#ac7951',
  paper = '#f4e6c7';
function envelope(p: Painter, x: number, y: number, z: number, w: number, h: number) {
  p.panel(x, y, z, w, h, paper);
  p.polygon(
    [
      [x, z + h],
      [x + w / 2, z + h * 0.45],
      [x + w, z + h],
    ].map(([a, b]) => project({ x: a, y }, b)),
    '#d6bc95'
  );
}
export function paintMailbox(p: Painter, o: WorldProp): void {
  p.box(0.13, 0.1, 0, o.width - 0.26, 0.8, 0.16, ink);
  p.box(0.25, 0.2, 0.16, o.width - 0.5, 0.65, 1.25, '#9d5146');
  p.box(0.08, 0.07, 1.41, o.width - 0.16, 0.88, 0.12, '#c27b5d');
  p.box(0.18, 0.14, 1.53, o.width - 0.36, 0.65, 0.47, oak);
  for (let i = 0; i < 3; i++) {
    const x = 0.26 + (i * (o.width - 0.5)) / 3;
    p.panel(x, 0.805, 1.61, (o.width - 0.7) / 3, 0.27, '#604e3c');
    envelope(p, x + 0.025, 0.81, 1.62, (o.width - 0.85) / 3, 0.16);
  }
  p.panel(0.42, 0.86, 0.98, o.width - 0.84, 0.09, ink);
  envelope(p, 0.65, 0.865, 0.42, 0.7, 0.41);
  p.box(0.1, 0.1, 2, o.width - 0.2, 0.78, 0.09, '#d1ac78');
}
export function paintTelephone(p: Painter, o: WorldProp): void {
  p.box(0, 0, 0, o.width, o.depth, 0.13, ink);
  p.box(0.06, 0.04, 0.13, o.width - 0.12, 0.12, 2.27, '#4f7770');
  for (const x of [0.04, o.width - 0.16])
    p.box(x, 0.08, 0.13, 0.12, o.depth - 0.16, 2.27, '#36665f');
  p.box(-0.03, -0.03, 2.4, o.width + 0.06, o.depth + 0.06, 0.13, '#c3a174');
  p.box(0.22, 0.18, 0.88, 0.9, 0.18, 1.05, '#b8c3b3');
  p.panel(0.48, 0.365, 1.55, 0.48, 0.24, '#2b5859');
  for (let z = 1.09; z < 1.48; z += 0.12)
    for (let x = 0.53; x < 0.9; x += 0.14) p.panel(x, 0.37, z, 0.08, 0.07, ink);
  p.box(0.25, 0.39, 1.22, 0.12, 0.16, 0.57, ink);
  p.box(0.21, 0.36, 1.17, 0.2, 0.22, 0.15, ink);
  p.box(0.21, 0.36, 1.74, 0.2, 0.22, 0.15, ink);
  tube(p, { x: 0.31, y: 0.42, z: 1.18 }, { x: 0.38, y: 0.45, z: 0.82 }, 0.018, ink, 6);
}
export function paintCalendar(p: Painter, o: WorldProp): void {
  for (const x of [0.18, o.width - 0.32]) p.box(x, 0.3, 0, 0.14, 0.28, 0.8, oak);
  p.box(0, 0.16, 0.7, o.width, 0.22, 1.62, ink);
  p.panel(0.12, 0.385, 0.84, o.width - 0.24, 1.32, paper);
  p.panel(0.12, 0.39, 1.93, o.width - 0.24, 0.23, '#bb6950');
  for (let col = 0; col < 7; col++)
    for (let row = 0; row < 4; row++) {
      const x = 0.2 + (col * (o.width - 0.4)) / 7,
        z = 0.96 + row * 0.23;
      p.panel(
        x,
        0.4,
        z,
        (o.width - 0.56) / 7,
        0.18,
        row === 2 && col === 3 ? '#84a391' : '#ded1b5'
      );
    }
  for (const x of [0.45, o.width - 0.55]) p.box(x, 0.2, 2.14, 0.1, 0.26, 0.28, '#ba9b60');
}
export function paintClock(p: Painter, o: WorldProp): void {
  p.box(0, 0, 0, o.width, o.depth, 0.18, oak);
  p.box(0.12, 0.1, 0.18, o.width - 0.24, o.depth - 0.2, 2.22, '#7d5e45');
  p.panel(0.25, o.depth - 0.09, 0.42, o.width - 0.5, 1.08, '#304b4b');
  tube(
    p,
    { x: o.width / 2, y: o.depth - 0.08, z: 0.61 },
    { x: o.width / 2, y: o.depth - 0.08, z: 1.5 },
    0.025,
    '#c5a55b',
    8
  );
  p.panel(o.width / 2 - 0.13, o.depth - 0.07, 0.54, 0.26, 0.25, '#dfbe70');
  const c = project({ x: o.width / 2, y: o.depth - 0.085 }, 1.95);
  p.ctx.save();
  p.ctx.translate(c.x, c.y);
  p.ctx.transform(1, 0.5, 0, -1, 0, 0);
  p.ctx.fillStyle = paper;
  p.ctx.beginPath();
  p.ctx.arc(0, 0, 11, 0, Math.PI * 2);
  p.ctx.fill();
  p.ctx.strokeStyle = ink;
  p.ctx.lineWidth = 1.3;
  p.ctx.beginPath();
  p.ctx.moveTo(0, 8);
  p.ctx.lineTo(0, 0);
  p.ctx.lineTo(6, -2);
  p.ctx.stroke();
  p.ctx.restore();
  p.box(0.03, 0.03, 2.4, o.width - 0.06, o.depth - 0.06, 0.12, oak);
}
export function paintWritingDesk(p: Painter, o: WorldProp): void {
  paintDesk(p, { ...o, tone: 'sage' });
  p.box(o.width - 0.76, 0.1, 0.9, 0.58, 0.45, 0.3, '#9d6950');
  p.panel(o.width - 0.7, 0.56, 1.02, 0.45, 0.035, '#ead3a8');
  tube(p, { x: 1.4, y: 0.8, z: 0.96 }, { x: 1.64, y: 0.61, z: 1.07 }, 0.025, ink, 8);
}
export function paintMeetingTable(p: Painter, o: WorldProp): void {
  paintTable(p, o);
  for (const x of [0.8, o.width - 1.1]) {
    p.box(x, 0.8, 0.74, 0.25, 0.25, 0.06, ink);
    tube(p, { x: x + 0.12, y: 0.92, z: 0.8 }, { x: x + 0.12, y: 0.76, z: 1.1 }, 0.025, ink, 8);
  }
  p.box(o.width / 2 - 0.38, 0.5, 0.74, 0.76, 0.6, 0.12, '#5b7d78');
  p.surface(o.width / 2 - 0.24, 0.64, 0.865, 0.48, 0.32, '#d0ddd0');
}

export function paintCounter(p: Painter, o: WorldProp): void {
  p.box(0.08, 0.08, 0, o.width - 0.16, o.depth - 0.16, 0.16, ink);
  p.box(0.04, 0.04, 0.16, o.width - 0.08, o.depth - 0.08, 0.84, '#597d70');
  for (let x = 0.18; x < o.width - 0.4; x += 1) {
    p.panel(x, o.depth - 0.035, 0.28, 0.75, 0.6, '#73927d');
    p.panel(x + 0.3, o.depth - 0.03, 0.77, 0.2, 0.025, '#ddc38e');
  }
  p.box(0, 0, 1, o.width, o.depth, 0.12, oak);
  for (let i = 0; i < 3; i++) {
    p.box(0.35 + i * 0.03, 0.2 + i * 0.03, 1.12 + i * 0.04, 0.7, 0.5, 0.035, paper);
  }
  p.box(o.width - 1.1, 0.2, 1.12, 0.56, 0.46, 0.12, '#a66a52');
  p.box(o.width - 0.88, 0.36, 1.24, 0.1, 0.12, 0.2, ink);
}
export function paintParcels(p: Painter, o: WorldProp): void {
  p.box(0.05, 0.05, 0, o.width - 0.1, o.depth - 0.1, 0.15, oak);
  for (const [x, y, z, w, d, h] of [
    [0.15, 0.1, 0.15, 0.75, 0.65, 0.55],
    [1, 0.2, 0.15, 0.7, 0.7, 0.8],
    [0.25, 0.2, 0.7, 0.55, 0.5, 0.4],
  ]) {
    p.box(x, y, z, w, d, h, '#b79566');
    p.box(x + w * 0.4, y, z + h, w * 0.14, d, 0.006, '#dac9a4');
    p.panel(x + 0.08, y + d + 0.005, z + 0.13, w * 0.55, 0.13, paper);
  }
}

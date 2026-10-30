import type { Painter } from './painter';
import type { WorldProp, Point } from '../types';
import { project } from '../geometry';
import { paintFloorSurface } from './floors';
import { floorVariant } from './prop-style';

import { POND_ROWS } from '../house-layout';
function rounded(p: Painter, points: Point[], fill: string | CanvasGradient): void {
  const c = p.ctx,
    corners = points.map(point => project(point));
  const last = corners.at(-1)!;
  c.beginPath();
  c.moveTo((last.x + corners[0].x) / 2, (last.y + corners[0].y) / 2);
  corners.forEach((point, i) => {
    const next = corners[(i + 1) % corners.length];
    c.quadraticCurveTo(point.x, point.y, (point.x + next.x) / 2, (point.y + next.y) / 2);
  });
  c.closePath();
  c.fillStyle = fill;
  c.fill();
}
/** One cached pond surface: rocky bank, shallows and deeper central water. */
export function paintPond(p: Painter, o: WorldProp): void {
  const c = p.ctx;
  // Reuse the surrounding lawn, including its opaque tile bleed. A flat mask
  // leaves a visible staircase and blue antialiasing seams around the bank.
  POND_ROWS.forEach((width, y) => {
    for (let x = 5 - width / 2; x < 5 + width / 2; x++) {
      const at = project({ x, y });
      c.save();
      c.translate(at.x, at.y);
      paintFloorSurface(p, 'grass', floorVariant('grass', o.x + x, o.y + y));
      c.restore();
    }
  });
  // Smooth the long bank contour; the concealed tile mask still owns collision.
  const shore: Point[] = [
    { x: 2.6, y: 0.18 },
    { x: 6.9, y: 0.18 },
    { x: 8.7, y: 1.25 },
    { x: 9.8, y: 2.5 },
    { x: 9.8, y: 4.55 },
    { x: 8.1, y: 5.7 },
    { x: 7.1, y: 6.65 },
    { x: 6.6, y: 7.8 },
    { x: 3.5, y: 7.8 },
    { x: 2.9, y: 6.65 },
    { x: 1.9, y: 5.7 },
    { x: 0.2, y: 4.55 },
    { x: 0.2, y: 2.5 },
    { x: 1.3, y: 1.25 },
  ];
  rounded(p, shore, '#b6b297');
  // Uneven sand and moss lie inside the existing shoreline, preserving its mask.
  for (let i = 0; i < shore.length; i++) {
    const a = shore[i],
      b = shore[(i + 1) % shore.length];
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const at = project({ x: 5 + (mid.x - 5) * 0.93, y: 4 + (mid.y - 4) * 0.93 });
    c.fillStyle = i % 3 ? '#c5bea3' : '#929f7c';
    c.beginPath();
    c.ellipse(at.x, at.y, 5 + (i % 3) * 2, 1.8 + (i % 2) * 0.5, 0, 0, Math.PI * 2);
    c.fill();
  }
  const water = shore.map(point => ({ x: 5 + (point.x - 5) * 0.9, y: 4 + (point.y - 4) * 0.86 }));
  rounded(p, water, '#78aaa0');
  const deep = c.createLinearGradient(-100, 60, 100, 190);
  deep.addColorStop(0, '#356b7d');
  deep.addColorStop(0.55, '#3c8791');
  deep.addColorStop(1, '#69a399');
  rounded(
    p,
    water.map(point => ({ x: 5 + (point.x - 5) * 0.84, y: 4 + (point.y - 4) * 0.78 })),
    deep
  );
  for (let i = 0; i < 14; i++) {
    const at = project({ x: 3.4 + (i % 4) * 0.8, y: 2 + Math.floor(i / 4) });
    c.fillStyle = i % 2 ? 'rgba(186,223,188,.18)' : 'rgba(11,77,88,.12)';
    c.beginPath();
    c.ellipse(at.x, at.y, 4 + (i % 3), 2, 0, 0, Math.PI * 2);
    c.fill();
  }
  c.strokeStyle = 'rgba(216,245,221,.45)';
  c.lineWidth = 1;
  for (const [x, y] of [
    [3.3, 2],
    [6.7, 3.3],
    [4.8, 5.6],
  ]) {
    const at = project({ x, y });
    c.beginPath();
    c.moveTo(at.x - 12, at.y);
    c.quadraticCurveTo(at.x, at.y + 2, at.x + 12, at.y - 1);
    c.stroke();
  }
}
export function paintPondLife(
  c: CanvasRenderingContext2D,
  prop: WorldProp,
  time: number,
  night = 0
): void {
  c.save();
  for (let i = 0; i < 2; i++) {
    // The derivative stays non-negative: each fish coasts, then briefly lingers.
    const clock = time * (0.11 + i * 0.015) + i * Math.PI;
    const phase = clock + Math.sin(clock) * 0.55;
    const at = project({ x: prop.x + 5 + Math.cos(phase) * 1.5, y: prop.y + 4 + Math.sin(phase) });
    c.save();
    c.translate(at.x, at.y);
    c.rotate(Math.atan2(Math.cos(phase) * 16, -Math.sin(phase) * 48));
    c.globalAlpha = 0.65 * (1 - night);
    c.fillStyle = i ? '#f1d2a1' : '#e59a63';
    c.beginPath();
    c.moveTo(6, 0);
    c.quadraticCurveTo(-1, -4, -5, 0);
    c.quadraticCurveTo(-1, 4, 6, 0);
    c.fill();
    c.beginPath();
    c.moveTo(-4, 0);
    c.lineTo(-8, -2 + Math.sin(time * 3) * 1.3);
    c.lineTo(-8, 2);
    c.closePath();
    c.fill();
    c.restore();
  }
  c.restore();
}

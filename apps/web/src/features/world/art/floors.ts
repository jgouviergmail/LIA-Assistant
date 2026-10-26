import { Painter, shade, type Sprite } from './painter';
import type { Ground } from '../types';
import { project } from '../geometry';
const COLORS: Record<Ground, string> = {
  marble: '#f3efdf',
  'violet-carpet': '#714e9b',
  carpet: '#31586c',
  checker: '#f1e9d2',
  slate: '#34284f',
  grass: '#68a351',
  path: '#d2c5a5',
  wood: '#bf8a52',
  tile: '#e5d6b9',
  deck: '#aa7444',
  water: '#359db7',
};
function grain(p: Painter, kind: Ground, variant: number, color: string): void {
  const c = p.ctx;
  for (let i = 0; i < 18; i++) {
    const x = ((i * 17 + variant * 11) % 97) / 100,
      y = ((i * 31 + variant * 7) % 97) / 100;
    const point = project({ x, y });
    c.fillStyle = shade(color, i % 3 === 0 ? 13 : -14);
    c.globalAlpha = kind === 'grass' ? 0.24 : 0.15;
    c.fillRect(point.x, point.y, i % 4 === 0 ? 1.4 : 0.65, 0.65);
  }
  c.globalAlpha = 1;
}
function boards(p: Painter, variant: number, color: string): void {
  const c = p.ctx;
  for (let row = 0; row < 3; row++) {
    const tint = shade(color, ((variant + row * 3) % 7) - 3);
    p.surface(0, row / 3, 0, 1, 1 / 3, tint);
    p.surface(0, row / 3, 0, 1, 0.012, shade(color, -22));
    p.surface(0, row / 3 + 0.016, 0, 1, 0.008, shade(color, 18));
    for (let line = 0; line < 3; line++) {
      c.strokeStyle = shade(tint, line === 0 ? 17 : -15);
      c.lineWidth = 0.45;
      c.globalAlpha = 0.33;
      const a = project({ x: 0.08 + (variant % 3) * 0.06, y: row / 3 + 0.09 + line * 0.065 });
      const b = project({ x: 0.7 + (variant % 2) * 0.16, y: row / 3 + 0.1 + line * 0.065 });
      c.beginPath();
      c.moveTo(a.x, a.y);
      c.lineTo(b.x, b.y);
      c.stroke();
    }
    c.globalAlpha = 1;
  }
  p.surface((variant % 4) * 0.25, 0, 0, 0.008, 1 / 3, shade(color, -16));
  p.surface(((variant + 2) % 4) * 0.25, 2 / 3, 0, 0.008, 1 / 3, shade(color, -16));
}
function stone(p: Painter, variant: number, color: string): void {
  const c = p.ctx;
  p.surface(0, 0, 0, 1, 0.009, shade(color, -14));
  p.surface(0, 0, 0, 0.009, 1, shade(color, -14));
  p.surface(0.014, 0.014, 0, 0.972, 0.012, shade(color, 12));
  if (variant % 3 === 0) p.surface(0.5, 0, 0, 0.008, 1, shade(color, -8));
  const a = project({ x: 0.22, y: 0.31 }),
    b = project({ x: 0.34, y: 0.36 }),
    d = project({ x: 0.43, y: 0.34 });
  c.globalAlpha = 0.18;
  c.strokeStyle = shade(color, -20);
  c.lineWidth = 0.5;
  c.beginPath();
  c.moveTo(a.x, a.y);
  c.lineTo(b.x, b.y);
  c.lineTo(d.x, d.y);
  c.stroke();
  c.globalAlpha = 1;
}
export function paintFloor(kind: Ground, variant: number): Sprite {
  const p = new Painter(1, 1, 0, 1);
  paintFloorSurface(p, kind, variant);
  return p.sprite();
}

/** Bake the same terrain detail into a larger authored surface without allocating tiles. */
export function paintFloorSurface(p: Painter, kind: Ground, variant: number): void {
  const c = p.ctx;
  const color = floorColor(kind, variant);
  const points = [
    project({ x: 0, y: 0 }),
    project({ x: 1, y: 0 }),
    project({ x: 1, y: 1 }),
    project({ x: 0, y: 1 }),
  ];
  // Continuous opaque bleed prevents seams when the cached terrain is zoomed.
  p.polygon(
    points.map(q => ({ x: q.x * 1.012, y: (q.y - 16) * 1.024 + 16 })),
    color
  );
  c.save();
  c.beginPath();
  points.forEach((q, i) => (i ? c.lineTo(q.x, q.y) : c.moveTo(q.x, q.y)));
  c.closePath();
  c.clip();
  DETAILS[kind](p, variant, color);
  if (kind !== 'checker') grain(p, kind, variant, color);
  c.restore();
}

function floorColor(kind: Ground, variant: number): string {
  return kind === 'checker'
    ? variant === 0
      ? '#f5ead5'
      : '#253441'
    : shade(COLORS[kind], (variant % 5) - 2);
}
function grass(p: Painter, variant: number, color: string): void {
  const c = p.ctx;
  for (let i = 0; i < 11; i++) {
    const x = ((i * 37 + variant * 11) % 97) / 100,
      y = ((i * 23 + variant * 17) % 91) / 100;
    const at = project({ x, y }),
      h = 1.1 + (i % 3) * 0.55;
    c.strokeStyle = shade(color, i % 2 ? 24 : -22);
    c.globalAlpha = 0.65;
    c.lineWidth = 0.65;
    c.beginPath();
    c.moveTo(at.x - 1.3, at.y);
    c.lineTo(at.x - 0.5, at.y - h);
    c.moveTo(at.x, at.y + 0.3);
    c.lineTo(at.x + 0.7, at.y - h * 0.8);
    c.stroke();
  }
  c.globalAlpha = 1;
  if (variant === 6 || variant === 7) {
    const at = project({ x: 0.37, y: 0.63 });
    c.fillStyle = variant === 6 ? '#f0d77a' : '#dae9a4';
    c.fillRect(at.x, at.y - 1, 1.25, 1.25);
  }
}
function water(p: Painter, _variant: number, color: string): void {
  for (let i = 0; i < 3; i++)
    p.surface(0.12 + i * 0.1, 0.18 + i * 0.24, 0, 0.45, 0.012, shade(color, 18 + i * 4));
}
const DETAILS: Record<Ground, (p: Painter, variant: number, color: string) => void> = {
  wood: boards,
  deck: boards,
  path: stone,
  tile: stone,
  marble: stone,
  slate: stone,
  water,
  grass,
  carpet: () => {},
  'violet-carpet': () => {},
  checker: () => {},
};

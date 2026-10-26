import { project } from '../geometry';
import type { Point, WorldProp } from '../types';
import { type Painter, shade } from './painter';
import { wallPalette } from './architecture-materials';
import { ACCENTS } from './palette';
import { wallProfile, WALL_BODY_THICKNESS } from './wall-profile';

function extrude(p: Painter, outline: Point[], z: number, height: number, color: string): void {
  for (let i = 0; i < outline.length; i++) {
    const a = outline[i],
      b = outline[(i + 1) % outline.length];
    if (b.x >= a.x && b.y <= a.y) continue;
    p.polygon(
      [project(a, z), project(b, z), project(b, z + height), project(a, z + height)],
      shade(color, b.y > a.y ? -30 : -7)
    );
  }
  p.polygon(
    outline.map(at => project(at, z + height)),
    shade(color, 14)
  );
}

function decorate(p: Painter, o: WorldProp): void {
  const side = o.wallConnections === 10;
  if (o.wallConnections !== 5 && !side) return;
  const panel = (u: number, z: number, w: number, h: number, c: string) =>
    p.panel(side ? 0.625 : u, side ? u : 0.625, z, w, h, c, side);
  if (o.wallFinish === 'brick') {
    for (let row = 0; row < 11; row++) {
      const z = 0.22 + row * 0.24;
      panel(0, z, 1, 0.018, '#dfad85');
      for (let col = 0; col < 2; col++)
        panel(col * 0.5 + (row % 2) * 0.25, z, 0.015, 0.24, '#dfad85');
    }
  } else if (o.wallFinish === 'oak') {
    panel(0, 0.18, 1, 0.65, '#ad7040');
    panel(0.08, 0.24, 0.84, 0.48, '#c58b54');
    panel(0, 0.84, 1, 0.05, '#e3b67a');
  }
  if (!o.wallWindow && o.wallFinish !== 'glass') return;
  const bottom = o.wallFinish === 'glass' ? 0.25 : 1;
  const height = o.wallFinish === 'glass' ? 2.1 : 1.35;
  panel(0.1, bottom, 0.8, height, '#f7e7c8');
  panel(0.16, bottom + 0.06, 0.68, height - 0.12, '#57b3ce');
  panel(0.2, bottom + 0.15, 0.1, height - 0.3, '#aee4ed');
  panel(0.48, bottom, 0.045, height, '#f9f0d6');
  panel(0.1, bottom + height * 0.55, 0.8, 0.045, '#f9f0d6');
  panel(0.07, bottom - 0.06, 0.86, 0.06, '#e4cfa8');
}

/** Every L/T/cross junction has one continuous body and one continuous coping. */
export function paintJoinedWall(p: Painter, o: WorldProp): void {
  const mask = o.wallConnections ?? 0,
    palette = wallPalette(o);
  const body = wallProfile(mask, WALL_BODY_THICKNESS),
    cap = wallProfile(mask, 0.34);
  const tall = o.height > 2;
  extrude(p, body, 0, o.height - 0.12, tall ? palette.body : '#344957');
  if (tall) decorate(p, o);
  extrude(p, cap, o.height - 0.12, 0.1, tall ? palette.cap : ACCENTS[o.tone]);
  extrude(p, cap, o.height - 0.02, 0.025, tall ? palette.edge : shade(ACCENTS[o.tone], 25));
}

export function paintParasol(p: Painter, o: WorldProp): void {
  const x = o.width / 2,
    y = o.depth / 2,
    top = o.height;
  p.box(x - 0.25, y - 0.25, 0, 0.5, 0.5, 0.12, '#536068');
  p.box(x - 0.035, y - 0.035, 0.12, 0.07, 0.07, top - 0.2, '#e3c69a');
  const corners = [
    { x: 0.1, y: 0.1 },
    { x, y: 0 },
    { x: o.width - 0.1, y: 0.1 },
    { x: o.width, y },
    { x: o.width - 0.1, y: o.depth - 0.1 },
    { x, y: o.depth },
    { x: 0.1, y: o.depth - 0.1 },
    { x: 0, y },
  ];
  const colors = [ACCENTS[o.tone], '#fff0ce'];
  corners.forEach((a, i) => {
    const b = corners[(i + 1) % corners.length];
    p.polygon(
      [project(a, top - 0.5), project(b, top - 0.5), project({ x, y }, top)],
      shade(colors[i % 2], i > 3 ? -8 : 5)
    );
    if (b.x < a.x || b.y > a.y)
      p.polygon(
        [
          project(a, top - 0.5),
          project(b, top - 0.5),
          project(b, top - 0.64),
          project(a, top - 0.64),
        ],
        shade(colors[i % 2], -20)
      );
  });
}

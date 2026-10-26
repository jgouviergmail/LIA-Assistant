import { project } from '../geometry';
import type { WorldProp } from '../types';
import { Painter, shade } from './painter';
import { propStyleVariant } from './prop-style';

/** Rounded, irregular foliage volumes. All facets are baked once into three reusable families. */
function foliage(
  p: Painter,
  x: number,
  y: number,
  z: number,
  radius: number,
  color: string,
  seed = 0
): void {
  const ring = Array.from({ length: 10 }, (_, i) => {
    const a = (i * Math.PI) / 5,
      r = radius * (0.9 + ((i * 7 + seed) % 5) * 0.035);
    return { x: x + Math.cos(a) * r, y: y + Math.sin(a) * r };
  });
  const scale = (q: (typeof ring)[number], factor: number, elevation: number) =>
    project({ x: x + (q.x - x) * factor, y: y + (q.y - y) * factor }, elevation);
  const faces = ring
    .map((a, i) => ({ a, b: ring[(i + 1) % ring.length], i }))
    .sort((a, b) => a.a.x + a.a.y + a.b.x + a.b.y - b.a.x - b.a.y - b.b.x - b.b.y);
  for (const { a, b, i } of faces) {
    const light = [-14, -23, -22, -15, -5, 6, 13, 16, 4, -5][i];
    p.polygon(
      [
        scale(a, 0.6, z - radius * 0.45),
        scale(b, 0.6, z - radius * 0.45),
        scale(b, 1, z),
        scale(a, 1, z),
      ],
      shade(color, light - 10)
    );
    p.polygon(
      [
        scale(a, 1, z),
        scale(b, 1, z),
        scale(b, 0.88, z + radius * 0.36),
        scale(a, 0.88, z + radius * 0.36),
      ],
      shade(color, light)
    );
  }
  for (const { a, b, i } of faces) {
    p.polygon(
      [
        scale(a, 0.88, z + radius * 0.36),
        scale(b, 0.88, z + radius * 0.36),
        scale(b, 0.43, z + radius * 0.7),
        scale(a, 0.43, z + radius * 0.7),
      ],
      shade(color, 8 + (i % 5) * 4)
    );
  }
  p.polygon(
    ring.map(q => scale(q, 0.43, z + radius * 0.7)),
    shade(color, 22)
  );
  // Small leaf planes break up the facets, following the same upper-left light.
  for (let i = 0; i < 5; i++) {
    const a = i * 2.4 + seed,
      r = radius * 0.22;
    const q = { x: x + Math.cos(a) * r, y: y + Math.sin(a) * r };
    p.surface(q.x, q.y, z + radius * 0.71, radius * 0.12, radius * 0.09, shade(color, 32 + i * 2));
  }
}
function branch(p: Painter, x: number, y: number, z: number, color: string): void {
  const start = project({ x: 0.5, y: 0.5 }, z - 0.48),
    end = project({ x, y }, z);
  p.polygon(
    [
      { x: start.x - 2, y: start.y },
      { x: end.x - 1.4, y: end.y },
      { x: end.x + 1.4, y: end.y + 1.5 },
      { x: start.x + 2, y: start.y + 2 },
    ],
    color
  );
}
function trunk(p: Painter, birch: boolean): void {
  const bark = birch ? '#e2ddca' : '#815035';
  p.box(0.41, 0.41, 0, 0.18, 0.18, 2.6, bark);
  for (let i = 0; i < 8; i++)
    p.panel(
      0.43 + (i % 2) * 0.055,
      0.593,
      0.15 + i * 0.27,
      0.075,
      birch ? 0.025 : 0.1,
      birch ? '#737268' : '#533b2e'
    );
  for (const [x, y] of [
    [0.26, 0.47],
    [0.58, 0.46],
    [0.45, 0.23],
  ])
    p.box(x, y, 0.015, 0.16, 0.12, 0.09, shade(bark, -12));
  branch(p, 0.13, 0.43, 1.5, bark);
  branch(p, 0.92, 0.52, 1.95, bark);
  branch(p, 0.35, 0.86, 2.2, bark);
}
function conifer(p: Painter): void {
  for (let tier = 0; tier < 5; tier++) {
    const r = 0.77 - tier * 0.13,
      z = 0.8 + tier * 0.46;
    const ring = Array.from({ length: 12 }, (_, i) => {
      const a = (i * Math.PI) / 6,
        radius = r * (i % 2 ? 0.78 : 1);
      return { x: 0.5 + Math.cos(a) * radius, y: 0.5 + Math.sin(a) * radius };
    });
    const faces = ring
      .map((a, i) => ({ a, b: ring[(i + 1) % 12], i }))
      .sort((a, b) => a.a.x + a.a.y + a.b.x + a.b.y - b.a.x - b.a.y - b.b.x - b.b.y);
    for (const { a, b, i } of faces) {
      p.polygon(
        [project(a, z), project(b, z), project({ x: 0.49, y: 0.48 }, z + 0.8)],
        shade('#287957', [-12, -19, -20, -9, -3, 8, 13, 20, 12, 5, -4, -10][i] + tier * 3)
      );
      p.polygon([project(a, z), project(b, z), project({ x: 0.5, y: 0.5 }, z - 0.12)], '#24553f');
    }
  }
}
export function paintTree(p: Painter, o: WorldProp): void {
  const variant = propStyleVariant(o),
    blossom = o.tone === 'clay',
    birch = !blossom && variant === 2;
  trunk(p, birch);
  if (!blossom && variant === 1) {
    conifer(p);
    return;
  }
  const leaf = blossom ? '#df699c' : birch ? '#79ae47' : '#36844d';
  // Overlapping crowns, not a vertical stack of identical cones.
  const lobes = birch
    ? [
        [0.19, 0.3, 1.55, 0.39],
        [0.71, 0.43, 1.75, 0.43],
        [0.32, 0.79, 1.95, 0.36],
        [0.23, 0.3, 2.18, 0.42],
        [0.68, 0.56, 2.4, 0.4],
        [0.45, 0.37, 2.8, 0.37],
      ]
    : [
        [0.25, 0.17, 1.5, 0.42],
        [0.84, 0.25, 1.66, 0.46],
        [0.02, 0.58, 1.67, 0.4],
        [0.49, 0.88, 1.72, 0.43],
        [0.95, 0.74, 1.95, 0.4],
        [0.11, 0.39, 2.05, 0.46],
        [0.57, 0.1, 2.16, 0.45],
        [0.55, 0.65, 2.31, 0.48],
        [0.39, 0.35, 2.7, 0.39],
      ];
  for (let i = 0; i < lobes.length; i++) {
    const [x, y, z, r] = lobes[i];
    const shift = blossom ? (variant - 1) * 0.08 : 0;
    foliage(
      p,
      x + shift,
      y - shift,
      z + ((i + variant) % 3) * 0.045,
      r * (blossom && variant === 2 ? 0.92 : 1),
      shade(leaf, (i % 4) * 7 - 9),
      i + variant
    );
  }
}

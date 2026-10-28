/** Original voxel garden artwork; all detail is baked into bounded cached sprites. */
import { project } from '../geometry';
import type { WorldProp } from '../types';
import { Painter, shade } from './painter';
import { propStyleVariant } from './prop-style';
import { seasonalPalette } from './seasonal-palette';

function crown(
  p: Painter,
  x: number,
  y: number,
  z: number,
  size: number,
  color: string,
  variant: number
): void {
  const blocks = [
    [0.12, 0.12, 0, 0.76, 0.72, 0.46, -12],
    [0, 0.25, 0.13, 0.61, 0.58, 0.34, -4],
    [0.37, 0.08, 0.24, 0.57, 0.6, 0.39, 3],
    [0.16, 0.48, 0.23, 0.6, 0.48, 0.36, -5],
    [0.2, 0.17, 0.5, 0.49, 0.56, 0.3, 13],
    [0.44, 0.34, 0.67, 0.33, 0.34, 0.18, 20],
    [0.08, 0.41, 0.47, 0.3, 0.32, 0.2, 7],
  ];
  for (const [bx, by, bz, w, d, h, tint] of blocks) {
    const offset = variant === 1 ? 0.035 : variant === 2 ? -0.025 : 0;
    p.box(
      x + (bx + offset) * size,
      y + by * size,
      z + bz * size,
      w * size,
      d * size,
      h * size,
      shade(color, tint)
    );
  }
  for (let i = 0; i < 5; i++) {
    const bx = 0.48 + ((i * 7 + variant * 3) % 5) * 0.035,
      by = 0.4 + ((i * 3 + variant) % 5) * 0.03;
    p.surface(
      x + bx * size,
      y + by * size,
      z + 0.855 * size,
      0.075 * size,
      0.055 * size,
      shade(color, 27)
    );
  }
}
export { paintTree as paintGardenTree } from './trees';
export function paintGardenPlant(p: Painter, o: WorldProp): void {
  const variant = propStyleVariant(o);
  const ceramic = ['#cfbca0', '#416d78', '#ac6551'][variant];
  p.box(0.22, 0.22, 0, 0.56, 0.56, 0.39, ceramic);
  for (let i = 0; i < 4; i++)
    p.panel(0.28 + i * 0.12, 0.781, 0.06, 0.025, 0.25, shade(ceramic, 18));
  p.box(0.16, 0.16, 0.35, 0.68, 0.68, 0.12, shade(ceramic, 22));
  p.surface(0.23, 0.23, 0.48, 0.54, 0.54, '#66533d');
  p.ctx.save();
  p.ctx.translate(p.reaction * 2.2, 0);
  p.box(0.47, 0.47, 0.46, 0.07, 0.07, 0.6, '#71825c');
  if (variant === 1) {
    for (let i = 0; i < 7; i++) {
      const x = 0.5 + Math.cos(i * 0.91) * 0.32,
        y = 0.5 + Math.sin(i * 0.91) * 0.31,
        z = 1.15 + (i % 3) * 0.17;
      p.polygon(
        [
          project({ x: 0.5, y: 0.5 }, 0.58),
          project({ x: x - 0.07, y }, z),
          project({ x, y: y + 0.07 }, z + 0.1),
          project({ x: x + 0.08, y }, z - 0.1),
        ],
        p.season === 'neutral'
          ? i % 2
            ? '#65a85b'
            : '#3b8552'
          : shade(seasonalPalette(p.season).leaf, i % 2 ? 12 : -8)
      );
    }
  } else if (variant === 2) {
    // Broad glossy leaves; a different silhouette from the compact shrub and blades.
    for (let i = 0; i < 6; i++) {
      const angle = i * 1.8,
        z = 0.66 + i * 0.12;
      const tip = { x: 0.5 + Math.cos(angle) * 0.4, y: 0.5 + Math.sin(angle) * 0.4 };
      const side = {
        x: Math.cos(angle + Math.PI / 2) * 0.12,
        y: Math.sin(angle + Math.PI / 2) * 0.12,
      };
      const mid = { x: (0.5 + tip.x) / 2, y: (0.5 + tip.y) / 2 };
      p.polygon(
        [
          project({ x: 0.5, y: 0.5 }, z),
          project({ x: mid.x + side.x, y: mid.y + side.y }, z + 0.25),
          project(tip, z + 0.17),
          project({ x: mid.x - side.x, y: mid.y - side.y }, z + 0.18),
        ],
        p.season === 'neutral'
          ? i % 2
            ? '#4b985b'
            : '#29754c'
          : shade(seasonalPalette(p.season).leaf, i % 2 ? 5 : -12)
      );
      const from = project({ x: 0.5, y: 0.5 }, z),
        to = project(tip, z + 0.17);
      p.ctx.beginPath();
      p.ctx.moveTo(from.x, from.y);
      p.ctx.lineTo(to.x, to.y);
      p.ctx.strokeStyle = '#91b76e';
      p.ctx.lineWidth = 0.6;
      p.ctx.stroke();
    }
  } else {
    crown(p, 0.12, 0.13, 0.88, 0.73, seasonalPalette(p.season).leaf, variant);
    p.box(0.52, 0.45, 1.32, 0.12, 0.12, 0.18, '#85b957');
  }
  p.ctx.restore();
}
export function paintGardenPlanter(p: Painter, o: WorldProp): void {
  const variant = propStyleVariant(o);
  p.box(0.03, 0.03, 0, o.width - 0.06, o.depth - 0.06, 0.39, '#ae9e85');
  p.box(0, 0, 0.34, o.width, o.depth, 0.1, '#d8cbb3');
  p.surface(0.09, 0.09, 0.445, o.width - 0.18, o.depth - 0.18, '#675841');
  for (let x = 0.16; x < o.width - 0.4; x += 0.55)
    crown(
      p,
      x + p.reaction * 0.04,
      0.15,
      0.47,
      0.54,
      p.season === 'neutral'
        ? variant === 2
          ? '#779467'
          : '#60825d'
        : seasonalPalette(p.season).leaf,
      variant
    );
  for (let x = 0.25; x < o.width - 0.1; x += 0.45)
    p.panel(x, o.depth + 0.001, 0.11, 0.015, 0.2, '#8f826f');
}
export function paintGardenFlowers(p: Painter, o: WorldProp): void {
  const variant = propStyleVariant(o);
  const petals = ['#e86b67', '#f2c14a', '#a782d8'];
  const palette = seasonalPalette(p.season);
  for (let i = 0; i < Math.max(1, 3 + variant + palette.flowers); i++) {
    const x = 0.12 + ((i * 7 + variant * 3) % 11) * 0.056,
      y = 0.12 + ((i * 3 + variant) % 10) * 0.065;
    const z = 0.1 + (i % 3) * 0.055;
    p.surface(x - 0.05, y - 0.04, 0.015, 0.24, 0.16, '#6c895c');
    p.box(x + 0.055, y + 0.055, 0.02, 0.035, 0.035, z, '#739261');
    const petal = p.season === 'neutral' ? petals[variant] : palette.petal;
    const bloom = 1 + Math.max(0, p.reaction) * 0.25;
    p.surface(x - 0.04, y + 0.02, z, 0.25 * bloom, 0.11, petal);
    p.surface(x + 0.03, y - 0.05, z + 0.005, 0.11, 0.25 * bloom, petal);
    p.box(x + 0.05, y + 0.05, z + 0.01, 0.065, 0.065, 0.045, '#f0d793');
  }
}

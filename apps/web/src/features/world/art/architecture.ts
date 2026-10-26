import { project } from '../geometry';
/** Original limestone and glazed joinery, baked once per shared material. */
import type { WorldProp } from '../types';
import type { Painter } from './painter';
import { shade } from './painter';
import { ACCENTS } from './palette';
import { hasInsetWindow, paintWallMaterial, wallPalette } from './architecture-materials';

export function paintWall(p: Painter, o: WorldProp, side: boolean, window: boolean): void {
  const palette = wallPalette(o);
  const w = side ? 0.18 : 1,
    d = side ? 1 : 0.18,
    accent = ACCENTS[o.tone];
  const panel = (u: number, z: number, width: number, height: number, color: string) =>
    p.panel(side ? 0.195 : u, side ? u : 0.195, z, width, height, color, side);
  p.box(0, 0, 0, w, d, 3, palette.body);
  // Continuous skirting, recessed panelling and a wood cap preserve the shell rhythm.
  p.box(0, 0, 0, side ? 0.24 : 1, side ? 1 : 0.24, 0.13, shade(accent, -12));
  panel(0, 0.13, 1, 0.47, shade(accent, 28));
  panel(0.07, 0.2, 0.86, 0.3, shade(accent, 34));
  panel(0, 0.59, 1, 0.045, '#f0e4ce');
  panel(0.97, 0.66, 0.018, 2.22, '#c9bea7');
  paintWallMaterial(p, o, side);
  p.box(0, 0, 2.9, side ? 0.26 : 1, side ? 1 : 0.26, 0.18, palette.cap);
  p.box(0, 0, 3.08, side ? 0.26 : 1, side ? 1 : 0.26, 0.045, palette.edge);
  if (!window || !hasInsetWindow(o)) return;
  paintWindow(p, side);
}
function paintWindow(p: Painter, side: boolean): void {
  const panel = (u: number, z: number, width: number, height: number, color: string) =>
    p.panel(side ? 0.195 : u, side ? u : 0.195, z, width, height, color, side);
  panel(0.115, 0.9, 0.77, 1.37, '#a9987a');
  panel(0.13, 0.93, 0.74, 1.31, '#f7efda');
  panel(0.19, 1, 0.62, 1.16, '#82b9bf');
  panel(0.21, 1.04, 0.57, 1.08, '#acd3d0');
  // Two restrained opaque reflections keep the solid occlusion mask exact.
  panel(0.25, 1.67, 0.1, 0.41, '#cfe4dc');
  panel(0.61, 1.08, 0.12, 0.35, '#b9dcd5');
  panel(0.475, 1, 0.04, 1.17, '#f8eed7');
  panel(0.19, 1.56, 0.63, 0.045, '#f8eed7');
  p.box(
    side ? 0.16 : 0.08,
    side ? 0.08 : 0.16,
    0.86,
    side ? 0.17 : 0.84,
    side ? 0.84 : 0.17,
    0.07,
    '#f2e7cc'
  );
}

function cornerTrim(p: Painter, z: number, h: number, color: string): void {
  const at = (x: number, y: number, height: number) => project({ x, y }, height);
  const front = (x: number, y: number, w: number, side: boolean) =>
    p.panel(x, y, z, w, h, shade(color, side ? -32 : -9), side);
  front(0.26, 0.26, 0.74, false);
  front(0.26, 0.26, 0.74, true);
  front(1, 0, 0.26, true);
  front(0, 1, 0.26, false);
  p.polygon(
    [
      [0, 0],
      [1, 0],
      [1, 0.26],
      [0.26, 0.26],
      [0.26, 1],
      [0, 1],
    ].map(([x, y]) => at(x, y, z + h)),
    shade(color, 13)
  );
}
export function paintWallCorner(p: Painter, o: WorldProp): void {
  const palette = wallPalette(o);
  paintWall(p, o, false, false);
  paintWall(p, o, true, false);
  // One L-shaped cap: overlapping boxes leave an exposed end face at the corner.
  cornerTrim(p, 0, 0.13, shade(ACCENTS[o.tone], -12));
  cornerTrim(p, 2.9, 0.18, palette.cap);
  cornerTrim(p, 3.08, 0.045, palette.edge);
}

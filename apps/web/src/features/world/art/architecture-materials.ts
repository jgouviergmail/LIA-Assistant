import type { WorldProp, WallFinish } from '../types';
import type { Painter } from './painter';
import { shade } from './painter';

interface WallPalette {
  body: string;
  cap: string;
  edge: string;
}
const PALETTES: Record<WallFinish, WallPalette> = {
  plaster: { body: '#f0e1c5', cap: '#365c53', edge: '#83a398' },
  oak: { body: '#ead8b7', cap: '#785c3c', edge: '#b99a68' },
  brick: { body: '#b97450', cap: '#385f56', edge: '#8da39a' },
  glass: { body: '#a2c8bf', cap: '#46786d', edge: '#b0c7a7' },
  acoustic: { body: '#344c4f', cap: '#b28754', edge: '#d5bb8b' },
  slate: { body: '#59767d', cap: '#b48b58', edge: '#d5bf93' },
};
export function wallPalette(prop: WorldProp): WallPalette {
  return PALETTES[prop.wallFinish ?? 'plaster'];
}
type Panel = (u: number, z: number, w: number, h: number, color: string) => void;
function brick(panel: Panel): void {
  // Running bond repeats at the tile edge, with no random per-wall texture.
  for (let row = 0; row < 10; row++) {
    const z = 0.65 + row * 0.22;
    panel(0, z, 1, 0.018, '#dfc3a2');
    for (let i = 0; i < 2; i++) {
      const x = i * 0.5 + (row % 2) * 0.25;
      panel(x, z, 0.016, 0.22, '#dfc3a2');
      panel(x + 0.035, z + 0.045, Math.min(0.38, 0.96 - x), 0.018, '#d0a486');
    }
  }
}
function glass(panel: Panel): void {
  panel(0.055, 0.65, 0.89, 2.15, '#bdd9c9');
  panel(0.1, 0.7, 0.8, 2.05, '#a8ccc2');
  panel(0.13, 1.75, 0.14, 0.85, '#d3e6d4');
  panel(0.29, 1.9, 0.045, 0.7, '#d3e6d4');
  panel(0.69, 0.8, 0.09, 0.45, '#cce0d0');
  panel(0, 0.6, 0.065, 2.3, '#447468');
  panel(0, 1.55, 1, 0.055, '#548373');
  panel(0, 2.77, 1, 0.055, '#548373');
}
function oak(panel: Panel): void {
  panel(0, 0.13, 1, 0.99, '#a27f54');
  panel(0.08, 0.25, 0.84, 0.7, '#b08f62');
  panel(0.12, 0.29, 0.76, 0.61, '#99764f');
  panel(0.14, 0.3, 0.72, 0.58, '#b79769');
  panel(0, 1.08, 1, 0.065, '#d0b17d');
}
function acoustic(panel: Panel): void {
  panel(0, 0.65, 1, 2.25, '#344c4f');
  for (let i = 0; i < 7; i++) {
    const u = 0.035 + i * 0.14;
    panel(u, 0.73, 0.07, 2.02, '#638079');
    panel(u, 0.73, 0.018, 2.02, '#97a492');
  }
  panel(0, 0.63, 1, 0.07, '#b58b58');
}
function slate(panel: Panel): void {
  panel(0, 0.66, 1, 2.22, '#59767d');
  panel(0.96, 0.68, 0.02, 2.18, '#456269');
  panel(0, 1.65, 1, 0.02, '#456269');
}
const DETAILS: Partial<Record<WallFinish, (panel: Panel) => void>> = {
  brick,
  glass,
  oak,
  acoustic,
  slate,
};
export function paintWallMaterial(p: Painter, o: WorldProp, side: boolean): void {
  const panel: Panel = (u, z, w, h, color) =>
    p.panel(side ? 0.2 : u, side ? u : 0.2, z, w, h, shade(color, side ? -12 : 0), side);
  DETAILS[o.wallFinish ?? 'plaster']?.(panel);
}

/** The same authored joinery determines both its silhouette and its night light. */
export function hasInsetWindow(prop: WorldProp): boolean {
  return (
    (prop.kind === 'window' || prop.kind === 'sideWindow' || prop.wallWindow === true) &&
    prop.wallFinish !== 'glass' &&
    prop.wallFinish !== 'acoustic'
  );
}

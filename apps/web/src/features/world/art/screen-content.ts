/** Finite public illustrations only; no user content is projected onto decor. */
import type { WorldProp } from '../types';
import { hasDecorScreen, type ScreenVariant } from '../decor-presentation';
import { Model, canonicalSize, orientModel, paintModel } from './model';
import type { Painter } from './painter';

export function screenModel(variant: ScreenVariant): Model {
  const m = new Model();
  m.panel(0, 0, 0, 1, 1, ['#174359', '#142a32', '#242c53', '#152a43', '#233e34'][variant]);
  if (variant === 0) {
    for (let i = 0; i < 4; i++)
      m.panel(0.12 + i * 0.2, 0.001, 0.12, 0.12, 0.25 + i * 0.16, ['#63c9ba', '#e9c673'][i % 2]);
  } else if (variant === 1) {
    for (let i = 0; i < 6; i++)
      m.panel(0.09, 0.001, 0.14 + i * 0.12, 0.3 + (i % 3) * 0.2, 0.035, '#93d7a6');
  } else if (variant === 2) {
    for (let i = 0; i < 16; i++)
      m.panel(0.07 + i * 0.055, 0.001, 0.5 + Math.sin(i * 0.8) * 0.25, 0.04, 0.07, '#d4b8f0');
  } else if (variant === 3) {
    m.panel(0.38, 0.001, 0.36, 0.25, 0.25, '#edca72');
    for (const [x, z] of [
      [0.12, 0.76],
      [0.73, 0.64],
      [0.2, 0.22],
      [0.82, 0.18],
    ])
      m.panel(x, 0.002, z, 0.035, 0.04, '#d9e8e1');
  } else {
    for (let i = 0; i < 3; i++) {
      m.panel(0.1, 0.001, 0.22 + i * 0.25, 0.8, 0.03, '#6c9885');
      m.panel(0.22 + i * 0.25, 0.001, 0.1, 0.03, 0.8, '#6c9885');
    }
    m.panel(0.48, 0.002, 0.48, 0.12, 0.14, '#efc56e');
  }
  return m;
}
export function paintScreenContent(p: Painter, prop: WorldProp): void {
  if (!p.decor.screen || !hasDecorScreen(prop) || (prop.facing ?? 1) >= 2) return;
  const { w, d } = canonicalSize(prop),
    desk = prop.kind === 'desk';
  const x = desk ? (w - 1.2) / 2 + 0.19 : 0.1;
  const y = desk ? 0.243 : d + 0.014;
  const z = desk ? 1.12 : 0.83,
    width = desk ? 0.65 : w - 0.2,
    height = desk ? 0.38 : 1.48;
  const parts = screenModel(p.decor.screen).parts.map(part =>
    part.kind === 'face'
      ? {
          ...part,
          points: part.points.map(point => ({
            x: x + point.x * width,
            y: y + point.y,
            z: z + point.z * height,
          })),
        }
      : part
  );
  paintModel(p, orientModel(parts, w, d, prop.facing ?? 1));
}

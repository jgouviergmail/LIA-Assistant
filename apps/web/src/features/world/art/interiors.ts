import { propStyleVariant } from './prop-style';
/** Authored interior objects; no random state, assets or per-frame decoration. */
import type { WorldProp } from '../types';
import type { Painter } from './painter';
import { shade } from './painter';
import { ACCENTS, DARK } from './palette';
import { FURNITURE } from './furniture-materials';
import { project } from '../geometry';

function legs(p: Painter, w: number, d: number, z: number): void {
  for (const x of [0.12, w - 0.25])
    for (const y of [0.12, d - 0.25]) p.box(x, y, 0, 0.12, 0.12, z, DARK);
}
function woodTop(p: Painter, w: number, d: number, z: number, color: string): void {
  p.surface(0.09, 0.09, z, w - 0.18, d - 0.18, shade(color, 14));
  for (let y = 0.22; y < d - 0.1; y += 0.24)
    p.surface(0.12, y, z + 0.001, w - 0.24, 0.012, shade(color, -3));
}
function book(
  p: Painter,
  x: number,
  y: number,
  z: number,
  w: number,
  d: number,
  color: string
): void {
  p.box(x, y, z, w, d, 0.07, color);
  p.box(x + 0.025, y + 0.025, z + 0.02, w - 0.05, d - 0.05, 0.05, '#e8dbbc');
  p.surface(x, y, z + 0.075, w, d, color);
}
export function paintRug(p: Painter, o: WorldProp): void {
  const accent = FURNITURE[o.tone].fabric,
    w = o.width,
    d = o.depth;
  p.box(0, 0, 0, w, d, 0.025, '#465058');
  p.surface(0.06, 0.06, 0.027, w - 0.12, d - 0.12, '#e7dbc0');
  for (const inset of [0.16, 0.28]) {
    for (const y of [inset, d - inset - 0.035])
      p.surface(inset, y, 0.03, w - inset * 2, 0.035, accent);
    for (const x of [inset, w - inset - 0.035])
      p.surface(x, inset, 0.03, 0.035, d - inset * 2, accent);
  }
  if (w >= 3 && d >= 3) {
    const cx = w / 2,
      cy = d / 2,
      a = Math.min(w, d) * 0.25;
    for (const [scale, color] of [
      [1, accent],
      [0.78, '#f5ead1'],
      [0.4, '#d6ad60'],
    ] as const)
      p.polygon(
        [
          project({ x: cx - a * scale, y: cy }),
          project({ x: cx, y: cy - a * scale }),
          project({ x: cx + a * scale, y: cy }),
          project({ x: cx, y: cy + a * scale }),
        ].map(point => ({ ...point, y: point.y - 1.1 })),
        color
      );
  }
  for (let x = 0.35; x < w - 0.3; x += 0.42) {
    p.surface(x, 0.025, 0.035, 0.13, 0.035, '#fff0d4');
    p.surface(x, d - 0.06, 0.035, 0.13, 0.035, '#fff0d4');
  }
}
export function paintDesk(p: Painter, o: WorldProp): void {
  const { frame, top } = FURNITURE[o.tone];
  legs(p, o.width, o.depth, 0.75);
  p.softBox(0, 0, 0.75, o.width, o.depth, 0.14, frame);
  woodTop(p, o.width, o.depth, 0.895, top);
  if (o.tone === 'sage') {
    p.box(0.25, 0.24, 0.9, 0.84, 0.54, 0.045, '#4d766e');
    p.box(0.29, 0.26, 0.945, 0.36, 0.5, 0.025, '#f3e7cd');
    p.box(0.68, 0.26, 0.945, 0.37, 0.5, 0.025, '#e8d9b9');
    for (let y = 0.36; y < 0.7; y += 0.09) {
      p.surface(0.33, y, 0.972, 0.25, 0.014, '#c8ba9b');
      p.surface(0.72, y, 0.972, 0.26, 0.014, '#c8ba9b');
    }
    p.surface(0.81, 0.26, 0.974, 0.05, 0.39, '#ac6553');
    p.box(o.width - 0.46, 0.22, 0.9, 0.16, 0.16, 0.3, '#b79b63');
    p.box(o.width - 0.4, 0.24, 1.2, 0.035, 0.035, 0.18, '#566c61');
    return;
  }
  const dx = (o.width - 1.2) / 2;
  p.box(dx + 0.35, 0.16, 0.9, 0.08, 0.12, 0.2, DARK);
  p.box(dx + 0.13, 0.14, 1.06, 0.78, 0.08, 0.54, DARK);
  p.panel(dx + 0.19, 0.23, 1.12, 0.65, 0.38, '#82b9c0');
  p.panel(dx + 0.23, 0.235, 1.4, 0.57, 0.055, '#daede4');
  p.panel(dx + 0.24, 0.236, 1.18, 0.14, 0.17, '#c3d8ce');
  for (let z = 1.19; z < 1.36; z += 0.06) p.panel(dx + 0.43, 0.237, z, 0.3, 0.018, '#e9edd9');
  p.box(dx + 0.24, 0.52, 0.91, 0.74, 0.24, 0.03, '#d9d8c8');
  for (let y = 0.56; y < 0.73; y += 0.055) p.surface(dx + 0.3, y, 0.945, 0.6, 0.014, '#929e92');
  p.box(o.width - 0.45, 0.4, 0.91, 0.16, 0.16, 0.17, '#c87f65');
  p.surface(o.width - 0.42, 0.43, 1.085, 0.1, 0.1, '#74594a');
  book(p, o.width - 0.85, 0.1, 0.91, 0.3, 0.34, '#547d7b');
}
export function paintTable(p: Painter, o: WorldProp): void {
  const { frame, top } = FURNITURE[o.tone];
  legs(p, o.width, o.depth, 0.6);
  p.softBox(0, 0, 0.6, o.width, o.depth, 0.12, frame, 0.025);
  woodTop(p, o.width, o.depth, 0.725, top);
  const variant = propStyleVariant(o);
  if (variant === 0) book(p, 0.25, 0.2, 0.73, 0.35, 0.38, '#476e72');
  else {
    p.surface(0.18, 0.17, 0.73, 0.6, 0.56, '#b65b4a');
    p.box(0.24, 0.22, 0.734, 0.44, 0.42, 0.025, '#f7f0dc');
    p.surface(0.3, 0.28, 0.761, 0.32, 0.3, '#e8d8b5');
    if (variant === 2) p.box(0.34, 0.32, 0.77, 0.2, 0.19, 0.07, '#b47d40');
  }
  p.box(o.width - 0.5, 0.35, 0.73, 0.18, 0.18, 0.18, '#eee3c8');
  p.surface(o.width - 0.47, 0.38, 0.915, 0.12, 0.12, '#7b624c');
}
export function paintBed(p: Painter, o: WorldProp): void {
  const frame = '#604333';
  p.box(0.08, 0.08, 0, o.width - 0.16, o.depth - 0.16, 0.3, frame);
  p.box(0, 0, 0.25, o.width, o.depth, 0.28, '#e7dfcb');
  p.box(0, 1.1, 0.54, o.width, o.depth - 1.1, 0.17, ACCENTS[o.tone]);
  p.surface(0.04, 1.17, 0.715, o.width - 0.08, 0.18, shade(ACCENTS[o.tone], 28));
  for (let y = 1.55; y < o.depth - 0.15; y += 0.4)
    p.surface(0.07, y, 0.716, o.width - 0.14, 0.016, shade(ACCENTS[o.tone], 10));
  p.box(0.22, 0.2, 0.56, o.width - 0.44, 0.7, 0.2, '#f1e7ce');
  p.surface(0.28, 0.27, 0.765, o.width - 0.56, 0.5, '#e9ddc2');
  p.box(0, 0, 0.2, o.width, 0.18, 1.1, frame);
  p.panel(0.13, 0.19, 0.49, o.width - 0.26, 0.59, '#b4c8c0');
  p.surface(0.03, o.depth - 0.8, 0.72, o.width - 0.06, 0.54, '#e9dfc1');
  for (let x = 0.17; x < o.width - 0.1; x += 0.28)
    p.surface(x, o.depth - 0.8, 0.724, 0.055, 0.54, '#426f80');
}
export function paintFountain(p: Painter, o: WorldProp): void {
  p.softBox(0, 0, 0, o.width, o.depth, 0.15, '#526e70');
  p.surface(0.16, 0.16, 0.255, o.width - 0.32, o.depth - 0.32, '#438c91');
  const center = project({ x: o.width / 2, y: o.depth / 2 }, 0.255);
  for (const radius of [15, 24, 32]) {
    p.ctx.beginPath();
    p.ctx.strokeStyle = '#a6d3cd';
    p.ctx.lineWidth = 0.8;
    p.ctx.ellipse(center.x, center.y, radius, radius / 2, 0, 0, Math.PI * 2);
    p.ctx.stroke();
  }
  // One continuous coping: overlapping beams let an end face erase the next top.
  const w = o.width,
    d = o.depth,
    rim = 0.16,
    top = 0.39;
  p.panel(0, d, 0.15, w, 0.24, '#cdd2bf');
  p.panel(w, 0, 0.15, d, 0.24, '#b8c0af', true);
  p.panel(rim, rim, 0.255, w - 2 * rim, top - 0.255, '#a7b8aa');
  p.panel(rim, rim, 0.255, d - 2 * rim, top - 0.255, '#c3cdbb', true);
  const outer = [
      [0, 0],
      [w, 0],
      [w, d],
      [0, d],
    ],
    inner = [
      [rim, rim],
      [rim, d - rim],
      [w - rim, d - rim],
      [w - rim, rim],
    ];
  p.polygon(
    [...outer, outer[0], ...inner, inner[0], outer[0]].map(([x, y]) => project({ x, y }, top)),
    '#e5e7d6'
  );
  p.softBox(1.27, 1.27, 0.2, 0.46, 0.46, 0.7, '#bba783');
  p.softBox(1.12, 1.12, 0.86, 0.76, 0.76, 0.1, '#a08c67');
  p.surface(1.17, 1.17, 0.965, 0.66, 0.66, '#bce0d5');
  p.box(1.42, 1.42, 0.96, 0.16, 0.16, 0.08, '#507c79');
}

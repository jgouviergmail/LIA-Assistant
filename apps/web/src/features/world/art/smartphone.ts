/** A small owner-local SMS reader on the atrium table; no text is baked in. */
import type { WorldProp } from '../types';
import type { Painter } from './painter';
export function paintSmartphone(p: Painter, o: WorldProp): void {
  // The support is the low atrium table, whose finished surface is at 0.725.
  const base = 0.725;
  p.softBox(0, 0, base, o.width, o.depth, 0.055, '#55696e', 0.015);
  p.box(0.2, 0.14, base + 0.055, 0.12, 0.16, 0.18, '#43585d');
  p.box(0.03, 0.18, base + 0.22, o.width - 0.06, 0.1, 0.64, '#294349');
  p.panel(0.08, 0.29, base + 0.31, o.width - 0.16, 0.43, '#a3d9d5');
  p.panel(0.13, 0.295, base + 0.41, o.width - 0.26, 0.2, '#f3f0de');
}

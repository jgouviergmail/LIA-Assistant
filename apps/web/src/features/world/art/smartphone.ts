/** A small owner-local SMS reader on the atrium table; no text is baked in. */
import type { WorldProp } from '../types';
import type { Painter } from './painter';
export function paintSmartphone(p: Painter, o: WorldProp): void {
  p.box(0, 0, 0.82, o.width, o.depth, 0.06, '#55696e');
  p.box(0.2, 0.14, 0.88, 0.12, 0.16, 0.2, '#43585d');
  p.box(0.03, 0.18, 1.04, o.width - 0.06, 0.1, 0.64, '#294349');
  p.panel(0.08, 0.29, 1.13, o.width - 0.16, 0.43, '#a3d9d5');
  p.panel(0.13, 0.295, 1.23, o.width - 0.26, 0.2, '#f3f0de');
}

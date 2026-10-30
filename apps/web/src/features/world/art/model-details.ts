import { Model } from './model';
import { shade } from './painter';
import { DARK, WOOD } from './palette';
export function modelTable(m: Model, w: number, d: number, color = WOOD): void {
  for (const x of [0.16, w - 0.3])
    for (const y of [0.16, d - 0.3]) m.box(x, y, 0, 0.14, 0.14, 0.82, DARK);
  m.softBox(0, 0, 0.82, w, d, 0.16, color, 0.035);
  m.surface(0.15, 0.13, 0.985, w - 0.3, 0.018, shade(color, 24));
  // A narrow apron recess separates the top from its supporting frame.
  m.panel(0.18, d - 0.05, 0.79, w - 0.36, 0.025, '#394741');
}
export function paper(m: Model, x: number, y: number, z = 1): void {
  m.box(x, y, z, 0.6, 0.5, 0.025, '#f4f0df');
  for (let i = 0; i < 3; i++)
    m.surface(x + 0.09, y + 0.12 + i * 0.09, z + 0.026, 0.35, 0.012, '#aaa995');
  m.surface(x + 0.68, y + 0.05, z + 0.018, 0.035, 0.4, '#254955');
}

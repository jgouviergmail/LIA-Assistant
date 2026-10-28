/** Three authored mechanisms: energy chamber, travelling gantry, paper processor. */
import type { WorldProp } from '../types';
import { Model } from './model';
import { ACCENTS, DARK } from './palette';

function chamber(m: Model, w: number, phase: number, active: boolean): void {
  const pulse = active ? Math.sin(phase * Math.PI * 6) * 0.14 : 0;
  m.box(0.35, 0.4, 1.35, w - 0.7, 0.8, 0.14, DARK);
  for (const x of [0.42, w - 0.55]) m.box(x, 0.47, 1.49, 0.13, 0.65, 0.9, '#b8c9b9');
  m.box(0.65, 0.62, 1.5, w - 1.3, 0.35, 0.68 + pulse, active ? '#9ce9d4' : '#67958e');
  const scanner = active ? Math.sin(phase * Math.PI) * 0.65 : 0;
  m.box(0.35, 0.38, 1.55 + scanner, w - 0.7, 0.16, 0.12, '#e3bb61');
  m.box(0.35, 0.4, 2.39, w - 0.7, 0.8, 0.13, DARK);
}
function gantry(m: Model, w: number, phase: number, active: boolean): void {
  for (const x of [0.35, w - 0.52]) {
    m.box(x, 0.4, 1.35, 0.17, 0.7, 1.14, '#aebaba');
    for (let i = 0; i < 5; i++)
      m.box(x - 0.04, 0.37, 1.48 + i * 0.18, 0.25, 0.16, 0.055, '#d0af71');
  }
  m.box(0.35, 0.4, 2.49, w - 0.7, 0.7, 0.12, DARK);
  const travel = active ? (0.5 - 0.5 * Math.cos(phase * Math.PI * 4)) * (w - 1.35) : 0;
  const press = active ? Math.max(0, Math.sin(phase * Math.PI * 6)) * 0.32 : 0;
  m.box(0.52 + travel, 0.45, 2.15 - press, 0.32, 0.36, 0.3, '#d1ac61');
  m.box(0.62 + travel, 0.52, 1.8 - press, 0.12, 0.2, 0.38, '#e1e9d7');
  m.box(0.65, 0.5, 1.37, w - 1.3, 0.5, 0.08, '#648879');
}
function processor(m: Model, w: number, d: number, phase: number, active: boolean): void {
  m.box(0.35, 0.32, 1.35, w - 0.7, 0.6, 0.95, '#405768');
  m.panel(0.48, 0.925, 1.57, w - 0.96, 0.52, '#172e3b');
  for (let i = 0; i < 4; i++) {
    const lit = active && Math.floor(phase * 12) % 4 === i;
    m.panel(
      0.56,
      0.93,
      1.64 + i * 0.1,
      (w - 1.12) * (lit ? 1 : 0.6),
      0.035,
      lit ? '#f2ce7d' : '#72b9ae'
    );
  }
  const feed = active ? Math.sin(phase * Math.PI) : 0;
  m.box(0.45, 0.98, 1.35, w - 0.9, d - 1.06, 0.1, DARK);
  if (feed > 0) {
    m.surface(0.55, 0.98, 1.46, w - 1.1, Math.max(0.05, (d - 1.1) * feed), '#f0ebd6');
    for (let i = 0; i < 3; i++)
      m.surface(0.68, 1.05 + i * 0.1 * feed, 1.465, w - 1.36, 0.025, '#7d9a90');
  }
}
export function machinery(m: Model, o: WorldProp, w: number, d: number, phase?: number): void {
  const color = ACCENTS[o.tone];
  m.box(0.1, 0.1, 0, w - 0.2, d - 0.2, 0.25, DARK);
  m.box(0.25, 0.25, 0.25, w - 0.5, d - 0.5, 1.1, color);
  for (const z of [0.6, 0.9, 1.2])
    m.panel(0.38, d - 0.24, z, 0.5, 0.06, phase === undefined ? '#a9b3a0' : '#e8d46e');
  if (o.tone === 'teal') chamber(m, w, phase ?? 0, phase !== undefined);
  else if (o.tone === 'violet') gantry(m, w, phase ?? 0, phase !== undefined);
  else processor(m, w, d, phase ?? 0, phase !== undefined);
}

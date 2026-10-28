import { jukeboxModel } from './jukebox';
import type { WorldProp } from '../types';
import { shade } from './painter';
import { Model } from './model';
import { ACCENTS, DARK, WOOD } from './palette';
import { modelTable, paper } from './model-details';
function seating(m: Model, o: WorldProp, w: number, d: number): void {
  const color = o.tone === 'clay' && o.kind === 'sofa' ? '#bd283e' : ACCENTS[o.tone],
    bench = o.kind === 'bench',
    seat = bench ? 0.62 : 0.73;
  for (const x of [0.2, w - 0.35])
    for (const y of [0.18, d - 0.3]) m.box(x, y, 0, 0.15, 0.12, 0.3, DARK);
  m.box(0.06, 0.06, 0.28, w - 0.12, d - 0.12, seat - 0.28, color);
  const count = bench ? 3 : 2;
  for (let i = 0; i < count; i++) {
    const x = 0.18 + (i * (w - 0.36)) / count;
    m.box(
      x,
      0.23,
      seat - 0.08,
      (w - 0.4) / count - 0.035,
      d - 0.31,
      0.08,
      bench ? '#b87d43' : shade(color, 14)
    );
  }
  for (const y of [0.08, 0.25]) if (bench) m.box(0.05, y, 0.85, w - 0.1, 0.1, 0.12, WOOD);
  if (!bench) m.box(0.04, 0.04, 0.58, w - 0.08, 0.18, 0.63, color);
  for (const x of [0.02, w - 0.17]) m.box(x, 0.05, seat, 0.15, d - 0.1, 0.25, color);
  if (!bench) {
    // Piping and two small contrasting cushions separate the back from its seat.
    m.panel(0.2, d - 0.075, seat - 0.015, w - 0.4, 0.018, shade(color, 43));
    for (const [x, cloth] of [
      [0.26, '#f1dba8'],
      [w - 0.68, '#416d7b'],
    ] as const) {
      m.box(x, 0.25, seat, 0.39, 0.25, 0.29, cloth);
      m.panel(x + 0.045, 0.503, seat + 0.08, 0.3, 0.025, '#f4e6c7');
    }
  }
}
function conference(m: Model, w: number, d: number): void {
  modelTable(m, w, d, '#53666d');
  m.surface(0.15, 0.15, 1, w - 0.3, d - 0.3, '#bd8d5c');
  for (const x of [0.6, 2.6, 4.6]) for (const y of [0.25, d - 0.85]) paper(m, x, y, 1.01);
  paper(m, 0.15, d / 2 - 0.2, 1.01);
  m.box(w / 2 - 0.17, d / 2 - 0.14, 1.01, 0.34, 0.28, 0.16, DARK);
  m.surface(w / 2 - 0.12, d / 2 - 0.08, 1.18, 0.24, 0.16, '#67d1d4');
}
function billiards(m: Model, w: number, d: number): void {
  modelTable(m, w, d, '#6e4430');
  m.box(0.05, 0.05, 0.9, w - 0.1, d - 0.1, 0.22, '#8e572b');
  m.surface(0.25, 0.25, 1.125, w - 0.5, d - 0.5, '#15845d');
  for (const x of [0.25, w / 2, w - 0.25])
    for (const y of [0.25, d - 0.25]) m.surface(x - 0.1, y - 0.1, 1.13, 0.2, 0.2, DARK);
  // The first cue ball is painted by the bounded local motion layer.
  for (let i = 1; i < 8; i++)
    m.box(
      w / 2 + (i % 3) * 0.18,
      1 + Math.floor(i / 3) * 0.2,
      1.14,
      0.13,
      0.13,
      0.1,
      ['#fff6d6', '#e8b63d', '#bc435b', '#3f74b1'][i % 4]
    );
  m.surface(0.5, 0.65, 1.14, w * 0.48, 0.035, '#e6bd70');
  m.surface(0.7, 1.3, 1.14, w * 0.35, 0.035, '#d4a45c');
}
function bar(m: Model, w: number, d: number): void {
  m.box(0.12, 0.12, 0.08, w - 0.24, d - 0.24, 1.03, '#743f2f');
  m.box(0.06, d - 0.18, 0.1, w - 0.12, 0.1, 0.12, '#392f2c');
  for (let x = 0.25; x < w - 0.3; x += 0.78) {
    const width = Math.min(0.63, w - 0.3 - x);
    m.panel(x, d - 0.055, 0.3, width, 0.62, '#ae6340');
    m.panel(x + 0.035, d - 0.052, 0.34, Math.max(0.02, width - 0.07), 0.035, '#d18c57');
  }
  m.box(0, 0, 1.1, w, d, 0.08, '#d0b984');
  m.box(-0.04, -0.04, 1.18, w + 0.08, d - 0.06, 0.12, '#61452e');
  m.surface(0.03, 0.03, 1.305, w - 0.06, d - 0.06, '#8a6141');
  m.box(0.15, d - 0.06, 0.23, w - 0.3, 0.045, 0.045, '#b8a26a');
  for (const x of [0.2, w - 0.25]) m.box(x, d - 0.22, 0.13, 0.04, 0.2, 0.1, '#b8a26a');
  m.surface(w - 0.85, 0.2, 1.31, 0.55, 0.5, '#899697');
  m.surface(w - 0.8, 0.25, 1.315, 0.45, 0.38, '#405763');
  m.box(w - 0.49, 0.14, 1.31, 0.04, 0.04, 0.28, '#cbd6d4');
  m.box(w - 0.49, 0.14, 1.55, 0.04, 0.25, 0.04, '#cbd6d4');
  for (let x = 0.6; x < w - 1.1; x += 1.5) {
    m.surface(x - 0.08, d - 0.45, 1.31, 0.34, 0.32, '#d8bd83');
    m.box(x, d - 0.4, 1.315, 0.13, 0.13, 0.22, '#dce9df');
    m.surface(x + 0.015, d - 0.385, 1.54, 0.1, 0.1, '#995b33');
  }
}
function bottles(m: Model, w: number, d: number): void {
  m.box(0.03, 0.03, 0.06, w - 0.06, d - 0.06, 0.8, '#815d3d');
  m.panel(0.08, d + 0.001, 0.18, w - 0.16, 0.55, '#b38654');
  m.box(0, 0, 0, 0.12, d, 2.5, WOOD);
  m.box(w - 0.12, 0, 0, 0.12, d, 2.5, WOOD);
  m.box(0, 0, 1, w, d, 0.12, WOOD);
  m.box(0, 0, 2, w, d, 0.12, WOOD);
  m.box(0, 0, 1, 0.12, d, 1.5, WOOD);
  m.box(w - 0.12, 0, 1, 0.12, d, 1.5, WOOD);
  for (let row = 0; row < 2; row++)
    for (let i = 0; i < Math.floor(w * 2); i++) {
      const x = 0.25 + i * 0.45,
        z = 1.12 + row;
      m.box(x, 0.04, z, 0.2, 0.2, 0.33, ['#2c825f', '#a44935', '#c78e36'][i % 3]);
      m.box(x + 0.06, 0.1, z + 0.33, 0.08, 0.08, 0.15, '#c4bf82');
      m.panel(x + 0.02, 0.245, z + 0.1, 0.16, 0.12, '#efe0ae');
    }
}
function crystal(m: Model, w: number, d: number): void {
  modelTable(m, w, d, '#452e62');
  m.surface(0.15, 0.15, 1, w - 0.3, d - 0.3, '#79438e');
  m.box(w / 2 - 0.32, d / 2 - 0.32, 1.01, 0.64, 0.64, 0.13, '#ddad43');
  const cx = w / 2,
    cy = d / 2,
    z = 1.55;
  const ring = [
    { x: cx - 0.43, y: cy, z },
    { x: cx, y: cy - 0.43, z },
    { x: cx + 0.43, y: cy, z },
    { x: cx, y: cy + 0.43, z },
  ];
  for (let i = 0; i < 4; i++) {
    const a = ring[i],
      b = ring[(i + 1) % 4];
    m.face([a, b, { x: cx, y: cy, z: 2.02 }], ['#8be0e7', '#62b6d2', '#b4f2f0', '#83c5e4'][i]);
    m.face([b, a, { x: cx, y: cy, z: 1.15 }], ['#557cb9', '#786cba', '#809edb', '#b3acdf'][i]);
  }
}
type Factory = (m: Model, o: WorldProp, w: number, d: number) => void;
const SOCIAL: Partial<Record<WorldProp['kind'], Factory>> = {
  cat: (m, _o, w, d) => {
    m.box(0.05, 0.12, 0.12, w - 0.1, d - 0.24, 0.28, '#26313d');
    for (const x of [0.07, w - 0.16])
      for (const y of [0.12, d - 0.21]) m.box(x, y, 0, 0.09, 0.09, 0.2, '#1d2731');
    m.box(0.04, d - 0.3, 0.35, w - 0.08, 0.26, 0.27, '#1b2632');
    m.box(0.04, d - 0.28, 0.62, 0.09, 0.11, 0.12, '#17212b');
    m.box(w - 0.13, d - 0.28, 0.62, 0.09, 0.11, 0.12, '#17212b');
    m.panel(0.09, d - 0.035, 0.48, 0.06, 0.045, '#e3d377');
    m.panel(w - 0.15, d - 0.035, 0.48, 0.06, 0.045, '#e3d377');
    m.box(w / 2 - 0.035, 0.01, 0.35, 0.07, 0.13, 0.25, '#25313e');
  },

  bench: seating,
  sofa: seating,
  meetingtable: (m, _o, w, d) => conference(m, w, d),
  billiards: (m, _o, w, d) => billiards(m, w, d),
  bar: (m, _o, w, d) => bar(m, w, d),
  bottles: (m, _o, w, d) => bottles(m, w, d),
  jukebox: (m, _o, w, d) => jukeboxModel(m, w, d),
  crystal: (m, _o, w, d) => crystal(m, w, d),
  lounger: (m, _o, w, d) => {
    for (const y of [0.2, d - 0.4]) m.box(0.1, y, 0, w - 0.2, 0.15, 0.4, DARK);
    m.box(0.05, 0.1, 0.4, w - 0.1, d - 0.2, 0.15, '#d9a467');
    for (let y = 0.2; y < d - 0.2; y += 0.32)
      m.surface(0.1, y, 0.56, w - 0.2, 0.25, ACCENTS[_o.tone]);
    m.box(0.1, 0.1, 0.56, w - 0.2, 0.7, 0.16, '#e7e1c4');
  },
};
export function socialModel(m: Model, o: WorldProp, w: number, d: number): boolean {
  const factory = SOCIAL[o.kind];
  if (!factory) return false;
  factory(m, o, w, d);
  return true;
}

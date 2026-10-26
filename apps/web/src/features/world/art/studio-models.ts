import type { WorldProp } from '../types';
import { Model } from './model';
import { ACCENTS, DARK, WOOD } from './palette';
import { propStyleVariant } from './prop-style';
import { modelTable, paper } from './model-details';

function gallerySymbol(m: Model, o: WorldProp, y: number): void {
  const ink = '#2c6c80';
  if (o.activity === 'asset-documents') {
    m.panel(0.38, y, 0.94, 0.55, 0.72, '#e8eff1');
    for (let i = 0; i < 4; i++) m.panel(0.46, y + 0.002, 1.08 + i * 0.11, 0.36, 0.025, ink);
  } else if (o.activity === 'asset-screenshots') {
    m.panel(0.25, y, 1.04, 0.8, 0.47, ink);
    m.panel(0.45, y, 1.51, 0.3, 0.12, ink);
    m.panel(0.52, y + 0.002, 1.15, 0.24, 0.24, '#9de4e3');
    m.panel(0.57, y + 0.004, 1.2, 0.14, 0.14, DARK);
  } else if (o.activity === 'asset-bookmarks') {
    m.face(
      [
        { x: 0.44, y, z: 1.65 },
        { x: 0.87, y, z: 1.65 },
        { x: 0.87, y, z: 0.94 },
        { x: 0.65, y, z: 1.1 },
        { x: 0.44, y, z: 0.94 },
      ],
      '#d55950'
    );
  } else {
    m.panel(0.23, y, 0.98, 0.85, 0.65, '#74c6d5');
    m.face(
      [
        { x: 0.23, y: y + 0.002, z: 0.98 },
        { x: 0.53, y: y + 0.002, z: 1.46 },
        { x: 0.76, y: y + 0.002, z: 1.1 },
        { x: 0.92, y: y + 0.002, z: 1.3 },
        { x: 1.08, y: y + 0.002, z: 0.98 },
      ],
      '#3a8b64'
    );
    m.panel(0.88, y + 0.004, 1.44, 0.11, 0.11, '#ffe18a');
  }
}
function easel(m: Model, o: WorldProp, w: number): void {
  for (const x of [0.1, w - 0.22]) m.box(x, 0.18, 0, 0.12, 0.16, 1.95, WOOD);
  m.box(w / 2 - 0.06, 0.75, 0, 0.12, 0.12, 1.7, WOOD);
  m.box(0.02, 0.22, 0.74, w - 0.04, 0.14, 1.15, '#bd8c55');
  m.panel(0.1, 0.365, 0.82, w - 0.2, 0.99, '#faf2d9');
  gallerySymbol(m, o, 0.369);
  m.box(0, 0.3, 0.7, w, 0.25, 0.08, WOOD);
  m.box(w / 2 - 0.12, 0.2, 1.9, 0.24, 0.2, 0.08, '#cb9c66');
}
function drawing(m: Model, w: number, d: number): void {
  modelTable(m, w, d);
  m.surface(0.3, 0.25, 1, w - 1, d - 0.5, '#f7edcd');
  m.surface(0.6, 0.45, 1.005, 1.3, 0.7, '#92d6dc');
  m.surface(0.7, 0.7, 1.01, 0.9, 0.3, '#66a572');
  m.surface(1.55, 0.53, 1.011, 0.13, 0.13, '#e9b54e');
  for (let i = 0; i < 4; i++) {
    m.surface(w - 0.55, 0.3 + i * 0.28, 1.005, 0.035, 0.21, '#b67738');
    m.surface(
      w - 0.55,
      0.5 + i * 0.28,
      1.006,
      0.035,
      0.06,
      ['#c64d51', '#2a987a', '#5655a8', '#dfac35'][i]
    );
  }
  m.box(w - 0.9, d - 0.45, 1, 0.24, 0.24, 0.3, '#387e8b');
}
function arcade(m: Model, o: WorldProp, w: number, d: number): void {
  const color = ACCENTS[o.tone];
  m.box(0.08, 0.08, 0, w - 0.16, d - 0.16, 0.9, DARK);
  m.box(0, 0.08, 0.1, 0.13, d - 0.16, 2.3, color);
  m.box(w - 0.13, 0.08, 0.1, 0.13, d - 0.16, 2.3, color);
  m.box(0.1, 0.12, 1, w - 0.2, 0.7, 1.13, DARK);
  m.panel(0.2, 0.825, 1.28, w - 0.4, 0.6, '#273f64');
  m.panel(0.27, 0.83, 1.36, w - 0.54, 0.09, '#71ded6');
  m.panel(0.45, 0.833, 1.63, 0.22, 0.14, '#f1c55d');
  m.box(0.08, 0.9, 0.91, w - 0.16, d - 0.9, 0.15, color);
  m.box(0.32, 1.07, 1.06, 0.1, 0.1, 0.14, DARK);
  for (let i = 0; i < 3; i++)
    m.box(0.65 + i * 0.16, 1.15, 1.06, 0.1, 0.1, 0.05, ['#e55f66', '#e7ba45', '#6dcf8e'][i]);
  m.box(0, 0.1, 2.13, w, 0.85, 0.28, color);
  m.panel(0.18, 0.956, 2.21, w - 0.36, 0.12, '#ffe4a2');
  m.panel(0.3, d - 0.07, 0.34, w - 0.6, 0.06, '#f2c55c');
}
function display(m: Model, _o: WorldProp, w: number, d: number): void {
  m.box(0, 0, 0.7, w, d, 1.75, DARK);
  m.panel(0.1, d + 0.002, 0.83, w - 0.2, 1.48, '#163d62');
  m.panel(0.3, d + 0.004, 1.95, w * 0.5, 0.1, '#65d7df');
  for (let i = 0; i < 3; i++)
    m.panel(
      0.35 + i * 0.5,
      d + 0.006,
      1.05,
      0.3,
      0.4 + i * 0.14,
      ['#486aac', '#2eb7b0', '#dfb34b'][i]
    );
  m.panel(w - 0.6, d + 0.005, 1.75, 0.22, 0.22, '#e6dba7');
  m.panel(w / 2 - 0.035, d + 0.008, 0.74, 0.07, 0.025, '#82d9d1');
}
function wallphone(m: Model): void {
  m.box(0.2, 0.03, 0.85, 0.65, 0.25, 1.5, '#d0d9d1');
  m.panel(0.36, 0.285, 1.75, 0.34, 0.22, '#72b9bd');
  for (let i = 0; i < 9; i++)
    m.panel(0.4 + (i % 3) * 0.1, 0.288, 1.38 + Math.floor(i / 3) * 0.1, 0.06, 0.06, DARK);
  m.box(0.05, 0.25, 1.25, 0.18, 0.18, 0.85, DARK);
  m.box(0.02, 0.22, 1.19, 0.3, 0.24, 0.15, DARK);
  m.box(0.02, 0.22, 2.04, 0.3, 0.24, 0.15, DARK);
  for (let i = 0; i < 7; i++)
    m.box(0.15 + (i % 2) * 0.055, 0.24, 0.95 + i * 0.035, 0.08, 0.07, 0.025, '#596967');
}
function posterArtwork(m: Model, o: WorldProp, w: number, d: number): void {
  const color = ACCENTS[o.tone],
    v = propStyleVariant(o),
    y = d + 0.008;
  m.box(0, 0, 1, w, d, 1.5, '#39494c');
  m.panel(0.06, d + 0.002, 1.06, w - 0.12, 1.38, '#f3e5c9');
  m.panel(0.13, d + 0.005, 1.2, w - 0.26, 1.1, v === 1 ? '#283f62' : color);
  if (v === 0) {
    m.face(
      [
        { x: 0.16, y, z: 1.25 },
        { x: w * 0.44, y, z: 2.08 },
        { x: w - 0.16, y, z: 1.25 },
      ],
      '#efe0aa'
    );
    m.face(
      [
        { x: w * 0.42, y: y + 0.002, z: 1.25 },
        { x: w * 0.7, y: y + 0.002, z: 1.79 },
        { x: w - 0.16, y: y + 0.002, z: 1.25 },
      ],
      '#3c6d70'
    );
    m.panel(w - 0.37, y + 0.004, 2.02, 0.13, 0.13, '#ffd57c');
  } else if (v === 1) {
    for (let i = 0; i < 7; i++)
      m.panel(0.23 + (i % 3) * 0.3, y, 1.4 + (i % 4) * 0.23, 0.035, 0.035, '#fff2cf');
    m.panel(w * 0.42, y + 0.002, 1.64, w * 0.22, 0.26, '#dc985e');
    m.panel(w * 0.23, y + 0.004, 1.75, w * 0.58, 0.035, '#e8cf9f');
  } else {
    for (let i = 0; i < 4; i++)
      m.panel(
        0.2 + (i * (w - 0.4)) / 4,
        y,
        1.33,
        (w - 0.48) / 4,
        0.35 + i * 0.16,
        ['#f1cf77', '#e67f59', '#e9dfbd', '#355f70'][i]
      );
  }
  m.panel(0.25, y + 0.006, 1.12, w - 0.5, 0.025, '#776752');
}
function poster(m: Model, o: WorldProp, w: number, d: number): void {
  const artwork = new Model();
  posterArtwork(artwork, o, w, d);
  // A framed print needs breathing space inside its wall bay. Retain its
  // authored anchor; narrow the complete artwork, including the opaque mask.
  const inset = w * 0.17,
    scale = 0.66;
  for (const part of artwork.parts) {
    m.parts.push(
      part.kind === 'box'
        ? { ...part, x: inset + part.x * scale, width: part.width * scale }
        : { ...part, points: part.points.map(p => ({ ...p, x: inset + p.x * scale })) }
    );
  }
}
function mirror(m: Model, w: number, d: number): void {
  m.box(0, 0, 0.45, w, d, 2, '#b2bebb');
  m.panel(0.06, d + 0.001, 0.52, w - 0.12, 1.85, '#9bc8d0');
  m.face(
    [
      { x: 0.15, y: d + 0.003, z: 0.6 },
      { x: w * 0.4, y: d + 0.003, z: 0.6 },
      { x: w - 0.15, y: d + 0.003, z: 2.25 },
      { x: w * 0.6, y: d + 0.003, z: 2.25 },
    ],
    '#c0e0e1'
  );
}
function alarm(m: Model, w: number, d: number): void {
  m.box(0, 0, 0.8, w, d, 0.29, DARK);
  m.panel(0.04, d + 0.002, 0.84, w - 0.08, 0.2, '#163c42');
  // Seven-segment style static face; actual local clock is painted by the bounded animation layer.
  for (const x of [0.08, 0.24, 0.47, 0.63]) {
    m.panel(x, d + 0.004, 0.88, 0.09, 0.018, '#85ead3');
    m.panel(x, d + 0.004, 1.0, 0.09, 0.018, '#85ead3');
  }
}
function promise(m: Model, w: number, d: number): void {
  m.box(0, 0, 1, w, d, 1.3, '#ae7e47');
  m.panel(0.1, d + 0.002, 1.1, w - 0.2, 1.1, '#e8d4ac');
  for (let i = 0; i < 3; i++) {
    m.panel(0.25, d + 0.006, 1.25 + i * 0.27, 0.17, 0.17, '#3b9b7f');
    m.panel(0.55, d + 0.009, 1.3 + i * 0.27, w - 0.8, 0.025, '#9b7958');
  }
}

type Factory = (m: Model, o: WorldProp, w: number, d: number) => void;
const STUDIO: Partial<Record<WorldProp['kind'], Factory>> = {
  easel,
  drawingtable: (m, _o, w, d) => drawing(m, w, d),
  arcade,
  display,
  wallphone: m => wallphone(m),
  poster,
  mirror: (m, _o, w, d) => mirror(m, w, d),
  alarm: (m, _o, w, d) => alarm(m, w, d),
  promiseboard: (m, _o, w, d) => promise(m, w, d),
  callbook: (m, _o, w, d) => {
    modelTable(m, w, d);
    m.box(0.35, 0.18, 1, w - 0.7, 0.6, 0.08, '#376f76');
    paper(m, 0.5, 0.23, 1.09);
  },
  nightstand: (m, _o, w, d) => {
    m.box(0, 0, 0.1, w, d, 0.65, WOOD);
    m.panel(0.1, d + 0.002, 0.26, w - 0.2, 0.36, '#bd925a');
    m.panel(w / 2 - 0.12, d + 0.004, 0.46, 0.24, 0.035, DARK);
    m.box(-0.02, -0.02, 0.75, w + 0.04, d + 0.04, 0.08, '#d5ab72');
  },
};
export function studioModel(m: Model, o: WorldProp, w: number, d: number): boolean {
  const factory = STUDIO[o.kind];
  if (!factory) return false;
  factory(m, o, w, d);
  return true;
}

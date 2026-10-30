/** Small public asset families; their detail is baked once, never rebuilt per frame. */
import { Model } from './model';
import { shade } from './painter';
import { propStyleVariant } from './prop-style';
import type { WorldProp } from '../types';
import { NO_DECOR, type DecorPresentation } from '../decor-presentation';
const BOOKS = ['#a24c40', '#37675d', '#c19b57', '#415c80', '#72516a', '#d3c5a0'];
function bookshelf(m: Model, o: WorldProp, w: number, d: number): void {
  const wood = '#79553d',
    inner = '#443629',
    v = propStyleVariant(o);
  m.box(0.04, 0.03, 0.05, w - 0.08, 0.08, 2.25, inner);
  for (const x of [0, w - 0.12]) m.box(x, 0, 0, 0.12, d, 2.4, wood);
  for (const z of [0.08, 0.65, 1.22, 1.79, 2.35]) {
    m.box(0.1, 0.01, z, w - 0.2, d - 0.01, 0.07, wood);
    m.panel(0.12, d + 0.002, z, w - 0.24, 0.035, '#d3a56a');
  }
  for (let row = 0; row < 4; row++) {
    let x = 0.19;
    for (let i = 0; x < w - 0.26; i++) {
      if (i === 3 && row === v) {
        for (let stack = 0; stack < 3; stack++) {
          m.box(
            x,
            d - 0.38,
            0.16 + row * 0.57 + stack * 0.085,
            0.48,
            0.32,
            0.075,
            BOOKS[(stack + v) % BOOKS.length]
          );
          m.panel(x + 0.025, d - 0.055, 0.18 + row * 0.57 + stack * 0.085, 0.43, 0.03, '#eadbc1');
        }
        x += 0.67;
        continue;
      }
      const bw = 0.13 + ((i + row + v) % 3) * 0.035,
        h = 0.3 + ((i * 3 + row + v) % 4) * 0.045;
      const y = d - 0.33,
        z = 0.16 + row * 0.57,
        color = BOOKS[(Math.floor(i / 3) + row * 2 + v) % BOOKS.length];
      m.box(x, y, z, bw, 0.28, h, color);
      m.panel(x + 0.025, d - 0.048, z + 0.055, bw - 0.05, 0.018, '#e9d9a8');
      if (i % 3 === 0) m.panel(x + 0.025, d - 0.047, z + h - 0.07, bw - 0.05, 0.025, '#e9d9a8');
      x += bw + 0.025;
    }
  }
}
function tablelamp(m: Model, o: WorldProp): void {
  const v = propStyleVariant(o),
    metal = v === 1 ? '#b39a5d' : '#3d555a';
  m.box(0.12, 0.12, 0.86, 0.36, 0.36, 0.035, metal);
  m.box(0.275, 0.275, 0.895, 0.05, 0.05, 0.37, metal);
  if (v === 1) {
    // A low green reading shade, with an exposed warm underside.
    m.box(0.06, 0.13, 1.25, 0.48, 0.32, 0.04, '#ffe8ae');
    m.box(0.04, 0.11, 1.29, 0.52, 0.36, 0.14, '#347864');
    m.box(0.11, 0.15, 1.43, 0.38, 0.27, 0.06, '#58927a');
    m.box(0.49, 0.42, 1.15, 0.015, 0.015, 0.18, '#c9af72');
    m.box(0.477, 0.407, 1.13, 0.04, 0.04, 0.04, '#c9af72');
    return;
  }
  if (v === 2) {
    m.box(0.12, 0.12, 1.17, 0.36, 0.36, 0.4, '#efdcb5');
    for (const z of [1.2, 1.3, 1.4, 1.5]) {
      m.panel(0.12, 0.482, z, 0.36, 0.014, '#b7a58b');
      m.face(
        [
          { x: 0.482, y: 0.12, z },
          { x: 0.482, y: 0.48, z },
          { x: 0.482, y: 0.48, z: z + 0.014 },
          { x: 0.482, y: 0.12, z: z + 0.014 },
        ],
        '#b7a58b'
      );
    }
    m.box(0.1, 0.1, 1.57, 0.4, 0.4, 0.025, metal);
    return;
  }
  const bottom = [
    { x: 0.04, y: 0.04, z: 1.25 },
    { x: 0.56, y: 0.04, z: 1.25 },
    { x: 0.56, y: 0.56, z: 1.25 },
    { x: 0.04, y: 0.56, z: 1.25 },
  ];
  const top = [
    { x: 0.17, y: 0.17, z: 1.56 },
    { x: 0.43, y: 0.17, z: 1.56 },
    { x: 0.43, y: 0.43, z: 1.56 },
    { x: 0.17, y: 0.43, z: 1.56 },
  ];
  for (let i = 0; i < 4; i++)
    m.face(
      [bottom[i], bottom[(i + 1) % 4], top[(i + 1) % 4], top[i]],
      ['#c5ac81', '#cfb88d', '#f3dcb1', '#e3c79b'][i]
    );
  m.face(top, '#f8e9c8');
  m.box(0.28, 0.28, 1.56, 0.04, 0.04, 0.04, metal);
}
function rock(m: Model, o: WorldProp, w: number, d: number): void {
  const v = propStyleVariant(o),
    h = 0.23 + v * 0.05;
  const top = [
    { x: 0.14 * w, y: 0.12 * d, z: h },
    { x: 0.8 * w, y: 0.06 * d, z: h + 0.05 },
    { x: 0.94 * w, y: 0.68 * d, z: h - 0.02 },
    { x: 0.25 * w, y: 0.95 * d, z: h - 0.04 },
  ];
  m.face(
    [top[0], top[1], { x: 0.94 * w, y: 0, z: 0 }, { x: 0.06 * w, y: 0.08 * d, z: 0 }],
    '#938f7b'
  );
  m.face(
    [top[3], top[0], { x: 0.06 * w, y: 0.08 * d, z: 0 }, { x: 0.12 * w, y: d, z: 0 }],
    '#888571'
  );
  m.face([top[2], top[3], { x: 0.12 * w, y: d, z: 0 }, { x: w, y: 0.8 * d, z: 0 }], '#827e6d');
  m.face([top[1], top[2], { x: w, y: 0.8 * d, z: 0 }, { x: 0.94 * w, y: 0, z: 0 }], '#9b9784');
  m.face(top, '#b8b49b');
  m.surface(0.3 * w, 0.24 * d, h + 0.055, 0.24 * w, 0.13 * d, '#c8c1a7');
}
function reeds(m: Model): void {
  for (let i = 0; i < 6; i++) {
    const x = 0.12 + (i % 3) * 0.2,
      y = 0.12 + Math.floor(i / 3) * 0.25,
      h = 0.55 + (i % 3) * 0.15;
    m.box(x, y, 0, 0.025, 0.025, h, '#5f8746');
    m.face(
      [
        { x, y, z: h * 0.7 },
        { x: x - 0.16, y: y + 0.04, z: h * 0.95 },
        { x: x - 0.04, y, z: h * 0.42 },
      ],
      '#85a651'
    );
    m.face(
      [
        { x, y, z: h * 0.55 },
        { x: x + 0.14, y: y + 0.12, z: h * 0.84 },
        { x: x + 0.04, y: y + 0.03, z: h * 0.3 },
      ],
      '#467950'
    );
    if (i % 2 === 0) m.box(x - 0.025, y - 0.025, h, 0.075, 0.075, 0.18, '#8f653d');
  }
}
function vegetables(m: Model, o: WorldProp, w: number, d: number): void {
  const v = propStyleVariant(o),
    edge = '#b48a57';
  m.box(0, 0, 0, w, d, 0.2, edge);
  m.surface(0.12, 0.12, 0.205, w - 0.24, d - 0.24, '#654831');
  for (let y = 0.45; y < d - 0.2; y += 0.6) {
    m.surface(0.18, y - 0.11, 0.211, w - 0.36, 0.2, '#755038');
    for (let x = 0.4; x < w - 0.2; x += 0.55) {
      const h = v === 2 ? 0.6 : 0.22;
      m.box(x, y, 0.22, 0.035, 0.035, h, '#568045');
      for (let leaf = 0; leaf < 3; leaf++) {
        const z = 0.25 + leaf * (v === 2 ? 0.16 : 0.045),
          size = 0.32 - leaf * 0.06;
        m.box(x - size / 2, y - size / 2, z, size, size, 0.045, shade('#4c9b4d', leaf * 13));
      }
      if (v === 1) m.box(x - 0.04, y - 0.035, 0.235, 0.1, 0.1, 0.12, '#e3a453');
      if (v === 2) m.box(x + 0.03, y + 0.02, 0.56, 0.095, 0.095, 0.095, '#d84d38');
    }
  }
  for (const x of [0.06, w - 0.14])
    for (const y of [0.06, d - 0.14]) m.box(x, y, 0, 0.08, 0.08, 0.28, '#d4ae7b');
  m.box(w - 0.35, 0.12, 0.22, 0.04, 0.04, 0.35, '#a08454');
  m.panel(w - 0.57, 0.165, 0.51, 0.48, 0.16, '#e9d7a5');
}
type Factory = (m: Model, o: WorldProp, w: number, d: number) => void;
const MODELS: Partial<Record<WorldProp['kind'], Factory>> = {
  sidetable: (m, _o, w, d) => {
    for (const x of [0.1, w - 0.2])
      for (const y of [0.1, d - 0.2]) m.box(x, y, 0, 0.1, 0.1, 0.76, '#4d5c59');
    m.box(0.04, 0.04, 0.76, w - 0.08, d - 0.08, 0.09, '#c3965d');
    m.surface(0.07, 0.07, 0.855, w - 0.14, d - 0.14, '#e1bb7d');
  },
  waterlily: (m, _o, w, d) => {
    m.surface(0.08, 0.08, 0.025, w * 0.65, d * 0.7, '#428b61');
    m.surface(0.32, 0.3, 0.03, w * 0.6, d * 0.55, '#62aa69');
    for (let i = 0; i < 5; i++) {
      const x = w * 0.55 + Math.cos(i * Math.PI * 0.4) * 0.1,
        y = d * 0.5 + Math.sin(i * Math.PI * 0.4) * 0.1;
      m.box(x, y, 0.04, 0.12, 0.12, 0.055, i % 2 ? '#eda3b8' : '#f6cad1');
    }
    m.box(w * 0.55, d * 0.5, 0.1, 0.08, 0.08, 0.04, '#f1cd67');
  },
  sink: (m, _o, w, d) => {
    m.box(0.1, 0.1, 0, w - 0.2, d - 0.2, 0.8, '#afbbb5');
    m.box(0, 0, 0.8, w, d, 0.12, '#f0ece0');
    m.surface(0.15, 0.16, 0.925, w - 0.3, d - 0.32, '#789b9d');
    m.surface(0.22, 0.23, 0.93, w - 0.44, d - 0.46, '#c8e0d9');
    m.box(w / 2 - 0.03, 0.08, 0.93, 0.06, 0.06, 0.2, '#a7bcbc');
    m.box(w / 2 - 0.03, 0.08, 1.1, 0.06, 0.24, 0.04, '#d3ddda');
  },
  shelf: bookshelf,
  tablelamp,
  rock,
  reeds: m => reeds(m),
  vegetable: vegetables,
};
export function refinedModel(
  m: Model,
  o: WorldProp,
  w: number,
  d: number,
  decor: DecorPresentation = NO_DECOR
): boolean {
  const draw = MODELS[o.kind];
  if (!draw) return false;
  draw(m, o, w, d);
  if (o.kind === 'tablelamp' && decor.light !== undefined) {
    m.panel(0.13, 0.489, 1.22, 0.34, 0.19, decor.light ? '#ffe6a0' : '#73877b');
  }
  return true;
}

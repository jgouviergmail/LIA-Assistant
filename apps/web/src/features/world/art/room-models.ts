import { propStyleVariant } from './prop-style';
import { chairModel } from './chairs';
import { FURNITURE } from './furniture-materials';
import { refinedModel } from './refined-models';
import { modelTable, paper } from './model-details';
import type { WorldProp } from '../types';
import { ACCENTS, DARK } from './palette';
import { Model, canonicalSize, orientModel, paintModel, type ModelPart } from './model';
import type { Painter } from './painter';
import { socialModel } from './social-models';
import { studioModel } from './studio-models';

function archive(m: Model, o: WorldProp, w: number, d: number): void {
  m.box(0, 0, 0, w, d, 0.14, '#514234');
  m.box(0, 0, 0.14, w, d, 2.3, '#36564e');
  const cols = Math.floor(w);
  for (let x = 0; x < cols; x++)
    for (let row = 0; row < 4; row++) {
      m.panel(x + 0.06, d + 0.001, 0.23 + row * 0.5, 0.88, 0.43, '#628374');
      m.panel(x + 0.27, d + 0.005, 0.45 + row * 0.5, 0.4, 0.12, '#f0e8d3');
      m.panel(x + 0.39, d + 0.008, 0.32 + row * 0.5, 0.18, 0.04, DARK);
      m.panel(
        x + 0.11,
        d + 0.007,
        0.48 + row * 0.5,
        0.08,
        0.07,
        ['#d8b66c', '#ad6559', '#6a92a1'][(row + propStyleVariant(o)) % 3]
      );
    }
  m.box(0, 0, 2.44, w, d, 0.12, '#8da18a');
}
function lab(m: Model, o: WorldProp, w: number, d: number): void {
  modelTable(m, w, d, '#577e81');
  const color = ACCENTS[o.tone];
  if (o.activity === 'skills') {
    m.box(0.25, 0.3, 1, 0.85, 0.65, 0.18, DARK);
    m.box(0.55, 0.5, 1.18, 0.16, 0.16, 0.5, color);
    m.box(0.55, 0.5, 1.68, 0.8, 0.18, 0.12, color);
    m.box(1.22, 0.5, 1.4, 0.13, 0.18, 0.38, '#f3cf75');
  } else if (o.activity === 'mcp') {
    for (const x of [0.25, 0.9, 1.55]) {
      m.box(x, 0.35, 1, 0.45, 0.6, 0.65, DARK);
      for (let i = 0; i < 3; i++) m.panel(x + 0.06, 0.956, 1.1 + i * 0.14, 0.3, 0.04, '#69e5d4');
    }
  } else {
    for (let i = 0; i < 3; i++)
      m.box(
        0.25 + i * 0.65,
        0.35 + (i % 2) * 0.18,
        1,
        0.5,
        0.5,
        0.3 + i * 0.15,
        ['#e8aa4e', '#9262ce', '#3ba99e'][i]
      );
  }
  m.surface(0.25, d - 0.3, 0.99, w - 0.5, 0.04, color);
  paper(m, w - 1, 0.15);
}
function machinery(m: Model, o: WorldProp, w: number, d: number): void {
  const color = ACCENTS[o.tone];
  m.box(0.1, 0.1, 0, w - 0.2, d - 0.2, 0.25, DARK);
  m.box(0.25, 0.25, 0.25, w - 0.5, d - 0.5, 1.1, color);
  for (const z of [0.6, 0.9, 1.2]) m.panel(0.38, d - 0.24, z, 0.5, 0.06, '#e8d46e');
  const variant = propStyleVariant(o);
  if (variant === 0) {
    m.box(w - 0.5, 0.4, 1.35, 0.18, 0.18, 1, '#7b96a0');
    m.box(0.35, 0.5, 1.4, 0.5, 0.5, 0.22, '#dfb66c');
    m.box(0.42, 0.57, 1.62, 0.36, 0.36, 0.54, '#8ce2d7');
    m.box(0.35, 0.5, 2.16, 0.5, 0.5, 0.1, DARK);
    m.box(0.85, 0.65, 1.55, 0.5, 0.12, 0.12, '#d4cfb4');
  } else if (variant === 1) {
    for (const x of [0.4, w - 0.7]) {
      m.box(x, 0.45, 1.35, 0.22, 0.22, 1.1, '#967b54');
      for (let i = 0; i < 5; i++)
        m.box(x - 0.08, 0.37, 1.48 + i * 0.18, 0.38, 0.38, 0.055, '#d0af71');
    }
    m.box(0.4, 0.45, 2.45, w - 0.88, 0.22, 0.12, '#8d9fa0');
  } else {
    m.box(0.35, 0.32, 1.35, w - 0.7, 0.6, 0.95, '#405768');
    m.panel(0.48, 0.925, 1.57, w - 0.96, 0.52, '#172e3b');
    for (let i = 0; i < 3; i++) m.panel(0.56, 0.93, 1.66 + i * 0.14, w - 1.12, 0.035, '#72d7ae');
    m.box(w - 0.55, 0.98, 1.35, 0.2, 0.2, 0.15, '#d8b77c');
  }
}
function weightbench(m: Model, o: WorldProp, w: number, d: number): void {
  m.box(0.1, 0.1, 0, 0.15, d - 0.2, 0.2, DARK);
  m.box(w - 0.25, 0.1, 0, 0.15, d - 0.2, 0.2, DARK);
  for (const y of [0.35, d - 0.5]) m.box(0.3, y, 0.2, w - 0.6, 0.15, 0.48, '#859b9f');
  m.box(0.4, 0.3, 0.65, w - 0.8, d - 0.6, 0.22, FURNITURE[o.tone].fabric);
  for (const x of [0.1, w - 0.25]) m.box(x, 0.4, 0.2, 0.15, 0.15, 1.6, '#9eafb3');
  m.box(0, 0.4, 1.55, w, 0.1, 0.1, '#e0e7df');
  for (const x of [0.05, w - 0.5]) m.box(x, 0.23, 1.35, 0.4, 0.44, 0.5, DARK);
}
function dumbbells(m: Model, w: number): void {
  for (const z of [0.35, 0.85]) {
    m.box(0.08, 0.12, z, w - 0.16, 0.7, 0.1, '#82939b');
    for (let i = 0; i < Math.floor(w); i++) {
      const x = 0.2 + i,
        size = 0.28 + i * 0.06 + z * 0.1;
      m.box(x, 0.45 - size / 2, z + 0.1, 0.16, size, size * 0.5, DARK);
      m.box(x + 0.45, 0.45 - size / 2, z + 0.1, 0.16, size, size * 0.5, DARK);
      m.box(x + 0.16, 0.4, z + 0.1 + size * 0.2, 0.29, 0.1, 0.08, '#e0e4df');
    }
  }
  for (const x of [0.15, w - 0.3]) m.box(x, 0.25, 0, 0.15, 0.4, 1.1, '#536b78');
}
function toilet(m: Model): void {
  m.box(0.08, 0.05, 0, 0.84, 0.27, 1, '#d8e2e0');
  m.box(0.14, 0.08, 1, 0.72, 0.22, 0.08, '#f7f4e9');
  m.box(0.3, 0.35, 0, 0.4, 0.5, 0.4, '#d5dddc');
  m.box(0.1, 0.28, 0.4, 0.8, 0.85, 0.16, '#f6f3e7');
  m.surface(0.23, 0.44, 0.565, 0.54, 0.52, '#8eaaa9');
  m.surface(0.3, 0.5, 0.57, 0.4, 0.39, '#d7ede9');
  m.surface(0.71, 0.14, 1.085, 0.12, 0.06, '#9caead');
}
type Factory = (m: Model, o: WorldProp, w: number, d: number) => void;
const MODELS: Partial<Record<WorldProp['kind'], Factory>> = {
  chair: (m, o) => chairModel(m, o),
  archive,
  readingdesk: (m, o, w, d) => {
    modelTable(m, w, d, o.activity === 'memories' ? '#abc2ba' : FURNITURE[o.tone].top);
    paper(m, 0.3, 0.25);
    m.box(w - 0.48, 0.2, 1, 0.25, 0.42, 0.1, ACCENTS[o.tone]);
  },
  labtable: lab,
  machine: machinery,
  weightbench,
  dumbbells: (m, _o, w) => dumbbells(m, w),
  toilet: m => toilet(m),
};
export function roomModel(o: WorldProp): ModelPart[] | null {
  const m = new Model(),
    { w, d } = canonicalSize(o);
  const factory = MODELS[o.kind];
  if (refinedModel(m, o, w, d)) return orientModel(m.parts, w, d, o.facing ?? 1);
  if (factory) factory(m, o, w, d);
  else if (!socialModel(m, o, w, d) && !studioModel(m, o, w, d)) return null;
  return orientModel(m.parts, w, d, o.facing ?? 1);
}
export function paintRoomModel(p: Painter, o: WorldProp): void {
  const model = roomModel(o);
  if (model) paintModel(p, model);
}

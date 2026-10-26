import { Model, type ModelVertex } from './model';
import { shade } from './painter';

/** Curved timber cabinet with a continuous brass/neon arch, glazed record and speaker cloth. */
function arch(w: number, inset: number, y: number, bottom: number): ModelVertex[] {
  const radius = w / 2 - inset,
    spring = 1.58;
  return [
    { x: inset, y, z: bottom },
    ...Array.from({ length: 17 }, (_, i) => {
      const angle = Math.PI - (i * Math.PI) / 16;
      return { x: w / 2 + Math.cos(angle) * radius, y, z: spring + Math.sin(angle) * radius };
    }),
    { x: w - inset, y, z: bottom },
  ];
}
function ring(
  m: Model,
  w: number,
  y: number,
  inset: number,
  thickness: number,
  color: string
): void {
  const outside = arch(w, inset, y, 0.19),
    inside = arch(w, inset + thickness, y + 0.002, 0.19);
  for (let i = 0; i < outside.length - 1; i++)
    m.face([outside[i], outside[i + 1], inside[i + 1], inside[i]], color);
}
function disc(m: Model, x: number, y: number, z: number, radius: number, color: string): void {
  m.face(
    Array.from({ length: 24 }, (_, i) => ({
      x: x + Math.cos((i * Math.PI) / 12) * radius,
      y,
      z: z + Math.sin((i * Math.PI) / 12) * radius,
    })),
    color
  );
}
export function jukeboxModel(m: Model, w: number, d: number): void {
  m.box(0.04, 0.02, 0.025, w - 0.08, d - 0.04, 0.13, '#25333b');
  const back = arch(w, 0.08, 0.1, 0.16),
    front = arch(w, 0.08, d - 0.02, 0.16);
  m.face(back, '#733629');
  for (let i = 0; i < front.length - 1; i++)
    m.face([back[i], back[i + 1], front[i + 1], front[i]], shade('#9e5133', i < 9 ? 12 : -13));
  m.face(front, '#643229');
  const y = d + 0.005;
  ring(m, w, y, 0.075, 0.055, '#d9a448');
  ring(m, w, y + 0.005, 0.14, 0.075, '#ffc977');
  ring(m, w, y + 0.01, 0.23, 0.025, '#e7cc8c');
  m.panel(0.29, y + 0.01, 0.27, w - 0.58, 0.72, '#222e38');
  // Woven grille, inset inside the lit side pillars.
  for (let x = 0.32; x < w - 0.3; x += 0.085) m.panel(x, y + 0.015, 0.3, 0.018, 0.65, '#897b62');
  for (let z = 0.33; z < 0.94; z += 0.085) m.panel(0.31, y + 0.017, z, w - 0.62, 0.012, '#baaa86');
  m.panel(0.3, y + 0.02, 1.1, w - 0.6, 0.73, '#4a898b');
  disc(m, w / 2, y + 0.025, 1.53, 0.27, '#162c38');
  disc(m, w / 2, y + 0.027, 1.53, 0.2, '#344650');
  disc(m, w / 2, y + 0.03, 1.53, 0.08, '#ee9b54');
  disc(m, w / 2, y + 0.033, 1.53, 0.022, '#f8df9c');
  m.face(
    [
      { x: 0.34, y: y + 0.034, z: 1.77 },
      { x: 0.44, y: y + 0.034, z: 1.77 },
      { x: w - 0.35, y: y + 0.034, z: 1.18 },
      { x: w - 0.45, y: y + 0.034, z: 1.18 },
    ],
    '#85b8b4'
  );
  m.panel(0.25, y + 0.04, 1, w - 0.5, 0.09, '#dbc894');
  for (let i = 0; i < 5; i++)
    m.panel(0.3 + (i * (w - 0.64)) / 5, y + 0.045, 1.015, 0.09, 0.045, '#f8edca');
  // Small centre medallion, coin slot and chrome bumper give scale without text.
  disc(m, w / 2, y + 0.045, 1.94, 0.075, '#e9c06c');
  m.panel(w / 2 - 0.06, y + 0.048, 1.925, 0.12, 0.025, '#78583a');
  m.panel(w - 0.25, y + 0.045, 0.85, 0.09, 0.025, '#38434a');
  m.box(0.07, d - 0.05, 0.15, w - 0.14, 0.075, 0.055, '#b1c1c0');
}

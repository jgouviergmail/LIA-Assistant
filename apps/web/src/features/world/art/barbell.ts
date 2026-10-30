/** Thin octagonal discs and a shaft kept over the chest during the actual lifts. */
import { barPosition, type DecorPresentation } from '../decor-presentation';
import { project } from '../geometry';
import {
  Model,
  canonicalSize,
  orientModel,
  paintModel,
  rotateModelPoint,
  type ModelPart,
  type ModelVertex,
} from './model';
import { Painter, shade, type Sprite } from './painter';
import type { Point, WorldProp } from '../types';
function disc(m: Model, x: number, y: number, z: number, radius: number): void {
  const thickness = 0.11;
  const ring = (at: number, r: number): ModelVertex[] =>
    Array.from({ length: 8 }, (_, i) => {
      const angle = ((i + 0.5) * Math.PI) / 4;
      return { x: at, y: y + Math.cos(angle) * r, z: z + Math.sin(angle) * r };
    });
  const back = ring(x, radius),
    front = ring(x + thickness, radius);
  m.face(back, '#35454d');
  m.face(ring(x, radius * 0.78), '#3e515a');
  m.face(ring(x, 0.065), '#bcc8c6');
  for (let i = 0; i < 8; i++)
    m.face(
      [back[i], back[(i + 1) % 8], front[(i + 1) % 8], front[i]],
      shade('#455760', Math.round(Math.sin((i * Math.PI) / 4) * 15))
    );
  m.face(front, '#273b46');
  m.face(ring(x + thickness, radius * 0.78), '#3e515a');
  m.face(ring(x + thickness, 0.065), '#bcc8c6');
}
export function barbellModel(width: number, decor: DecorPresentation): ModelPart[] {
  const m = new Model();
  const { y, z } = barPosition(decor);
  // Split at every plate face: one long shaft painted first was erased by the
  // far plate silhouette, making it appear attached to the rim instead of the hub.
  const ends = [
    0,
    0.02,
    0.13,
    0.15,
    0.26,
    width - 0.26,
    width - 0.15,
    width - 0.13,
    width - 0.02,
    width,
  ];
  for (let i = 1; i < ends.length; i++)
    m.box(ends[i - 1], y, z, ends[i] - ends[i - 1], 0.08, 0.08, '#cbd8d7');
  for (const x of [0.15, width - 0.26]) disc(m, x, y + 0.04, z + 0.04, 0.33);
  for (const x of [0.02, width - 0.13]) disc(m, x, y + 0.04, z + 0.04, 0.25);
  return m.parts;
}
/** The racked bar a lift starts from; every later position is this sprite moved. */
const RACKED: DecorPresentation = Object.freeze({ press: 0, barReach: 0 });
export function paintHeldBarbell(prop: WorldProp, ratio: number): Sprite {
  const { w, d } = canonicalSize(prop);
  const painter = new Painter(prop.width, prop.depth, 2.5, ratio);
  paintModel(painter, orientModel(barbellModel(w, RACKED), w, d, prop.facing ?? 1));
  return painter.sprite();
}
/** Screen offset of a lift from the racked bar: a rigid body under a linear projection. */
export function heldBarbellOffset(prop: WorldProp, decor: DecorPresentation): Point {
  const { w, d } = canonicalSize(prop);
  const screen = (value: DecorPresentation) => {
    const at = rotateModelPoint({ x: 0, ...barPosition(value) }, w, d, prop.facing ?? 1);
    return project(at, at.z);
  };
  const racked = screen(RACKED),
    lifted = screen(decor);
  return { x: lifted.x - racked.x, y: lifted.y - racked.y };
}

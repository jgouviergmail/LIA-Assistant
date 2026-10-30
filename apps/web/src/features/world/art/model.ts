/** Pure, inspectable authored geometry. Baked once into the existing sprite cache. */
import type { Facing } from './actor-direction';
import type { WorldProp } from '../types';
import type { Painter } from './painter';
import { project } from '../geometry';
import { orderedModelParts } from './model-order';
export interface ModelVertex {
  x: number;
  y: number;
  z: number;
}
export type ModelPart =
  | {
      kind: 'box';
      x: number;
      y: number;
      z: number;
      width: number;
      depth: number;
      height: number;
      color: string;
      bevel?: number;
    }
  | { kind: 'face'; points: readonly ModelVertex[]; color: string };
export class Model {
  readonly parts: ModelPart[] = [];
  box(
    x: number,
    y: number,
    z: number,
    width: number,
    depth: number,
    height: number,
    color: string
  ): void {
    this.parts.push({ kind: 'box', x, y, z, width, depth, height, color });
  }
  /** Rounded corners keep the same support plane and bounds as a box. */
  softBox(
    x: number,
    y: number,
    z: number,
    width: number,
    depth: number,
    height: number,
    color: string,
    bevel = 0.04
  ): void {
    this.parts.push({ kind: 'box', x, y, z, width, depth, height, color, bevel });
  }
  surface(x: number, y: number, z: number, w: number, d: number, color: string): void {
    this.face(
      [
        { x, y, z },
        { x: x + w, y, z },
        { x: x + w, y: y + d, z },
        { x, y: y + d, z },
      ],
      color
    );
  }
  panel(x: number, y: number, z: number, w: number, h: number, color: string): void {
    this.face(
      [
        { x, y, z },
        { x: x + w, y, z },
        { x: x + w, y, z: z + h },
        { x, y, z: z + h },
      ],
      color
    );
  }
  face(points: readonly ModelVertex[], color: string): void {
    this.parts.push({ kind: 'face', points, color });
  }
}
export function rotateModelPoint(
  p: ModelVertex,
  w: number,
  d: number,
  facing: Facing
): ModelVertex {
  switch (facing) {
    case 0:
      return { x: p.y, y: w - p.x, z: p.z };
    case 2:
      return { x: d - p.y, y: p.x, z: p.z };
    case 3:
      return { x: w - p.x, y: d - p.y, z: p.z };
    default:
      return p;
  }
}
export function orientModel(
  parts: readonly ModelPart[],
  w: number,
  d: number,
  facing: Facing
): ModelPart[] {
  return parts.map(part => {
    if (part.kind === 'face')
      return { ...part, points: part.points.map(p => rotateModelPoint(p, w, d, facing)) };
    const p = rotateModelPoint(part, w, d, facing),
      q = rotateModelPoint(
        { ...part, x: part.x + part.width, y: part.y + part.depth },
        w,
        d,
        facing
      );
    return {
      ...part,
      x: Math.min(p.x, q.x),
      y: Math.min(p.y, q.y),
      width: Math.abs(p.x - q.x),
      depth: Math.abs(p.y - q.y),
    };
  });
}
export function paintModel(p: Painter, parts: readonly ModelPart[]): void {
  for (const part of orderedModelParts(parts)) {
    if (part.kind === 'box') {
      if (part.bevel === undefined)
        p.box(part.x, part.y, part.z, part.width, part.depth, part.height, part.color);
      else
        p.softBox(
          part.x,
          part.y,
          part.z,
          part.width,
          part.depth,
          part.height,
          part.color,
          part.bevel
        );
    } else
      p.polygon(
        part.points.map(q => project(q, q.z)),
        part.color
      );
  }
}
export function canonicalSize(o: WorldProp): { w: number; d: number } {
  const swap = o.facing === 0 || o.facing === 2;
  return { w: swap ? o.depth : o.width, d: swap ? o.width : o.depth };
}

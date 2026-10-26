/** Small orthographic mesh baked to the existing bounded sprite cache. No WebGL. */
import { actorPoint } from './actor-direction';
import { Painter, shade, type Sprite } from './painter';
import { project } from '../geometry';
interface Vertex {
  x: number;
  y: number;
  z: number;
}
interface Face {
  vertices: Vertex[];
  color: string;
  light: number;
  depth: number;
  details: Face[];
}
export class ActorMesh {
  private faces: Face[] = [];
  private fronts: { x: number; y: number; z: number; w: number; h: number; face: Face }[] = [];
  constructor(
    private heading: number,
    private lieHeight?: number
  ) {}
  private vertex(x: number, y: number, z: number): Vertex {
    if (this.lieHeight !== undefined)
      return { ...actorPoint({ x, y: 1.5 - z }, this.heading), z: this.lieHeight + y - 0.15 };
    return { ...actorPoint({ x, y }, this.heading), z };
  }
  private face(
    vertices: Vertex[],
    normal: { x: number; y: number; z: number },
    color: string,
    parent?: Face
  ): Face | null {
    if (this.lieHeight !== undefined) normal = { x: normal.x, y: -normal.z, z: normal.y };
    const angle = (this.heading * Math.PI) / 4 - Math.PI / 2;
    const nx = normal.x * Math.cos(angle) - normal.y * Math.sin(angle);
    const ny = normal.x * Math.sin(angle) + normal.y * Math.cos(angle);
    if (nx + ny + normal.z <= 1e-7) return null;
    const light = normal.z ? 13 : -20 - 12 * nx + 12 * ny;
    const depth = vertices.reduce((sum, p) => sum + p.x + p.y + p.z, 0) / vertices.length;
    const face = { vertices, color, light, depth, details: [] };
    if (parent) parent.details.push(face);
    else this.faces.push(face);
    return face;
  }
  box(x: number, y: number, z: number, w: number, d: number, h: number, color: string): void {
    const p = (a: number, b: number, c: number) => this.vertex(a, b, c);
    this.face(
      [p(x, y, z + h), p(x + w, y, z + h), p(x + w, y + d, z + h), p(x, y + d, z + h)],
      { x: 0, y: 0, z: 1 },
      color
    );
    const front = this.face(
      [p(x, y + d, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x, y + d, z + h)],
      { x: 0, y: 1, z: 0 },
      color
    );
    if (front) this.fronts.push({ x, y: y + d, z, w, h, face: front });
    this.face(
      [p(x + w, y, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x + w, y, z + h)],
      { x: 1, y: 0, z: 0 },
      color
    );
    this.face(
      [p(x, y, z), p(x + w, y, z), p(x + w, y, z + h), p(x, y, z + h)],
      { x: 0, y: -1, z: 0 },
      color
    );
    this.face(
      [p(x, y, z), p(x, y + d, z), p(x, y + d, z + h), p(x, y, z + h)],
      { x: -1, y: 0, z: 0 },
      color
    );
  }
  front(x: number, y: number, z: number, w: number, h: number, color: string): void {
    // Coplanar facial/clothing details belong to their surface, so face sorting
    // cannot paint the skin over an eye or put a collar over a foreground arm.
    const surface = this.fronts
      .filter(
        p =>
          Math.abs(p.y - y) < 0.04 &&
          x >= p.x - 0.001 &&
          x + w <= p.x + p.w + 0.001 &&
          z >= p.z - 0.001 &&
          z + h <= p.z + p.h + 0.001
      )
      .sort((a, b) => Math.abs(a.y - y) - Math.abs(b.y - y))[0];
    if (surface)
      this.face(
        [
          this.vertex(x, y, z),
          this.vertex(x + w, y, z),
          this.vertex(x + w, y, z + h),
          this.vertex(x, y, z + h),
        ],
        { x: 0, y: 1, z: 0 },
        color,
        surface.face
      );
  }
  sprite(ratio: number): Sprite {
    const painter = new Painter(1, 1, 2.6, ratio);
    // View rays have direction (1,1,1) under this world's 2:1 projection.
    this.faces.sort((a, b) => a.depth - b.depth);
    for (const face of this.faces) {
      painter.polygon(
        face.vertices.map(p => project(p, p.z)),
        shade(face.color, face.light)
      );
      for (const detail of face.details)
        painter.polygon(
          detail.vertices.map(p => project(p, p.z)),
          shade(detail.color, detail.light)
        );
    }
    const sprite = painter.sprite();
    return { ...sprite, anchorY: sprite.anchorY + 16 };
  }
}

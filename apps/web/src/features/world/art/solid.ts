/** Faceted static solids, baked once; all normals share the world's light direction. */
import { project } from '../geometry';
import { shade, type Painter } from './painter';
export interface Vertex {
  x: number;
  y: number;
  z: number;
}
export function tube(
  p: Painter,
  a: Vertex,
  b: Vertex,
  radius: number,
  color: string,
  sides = 12
): void {
  const dx = b.x - a.x,
    dy = b.y - a.y,
    dz = b.z - a.z,
    length = Math.hypot(dx, dy, dz);
  if (length < 1e-6) return;
  const axis = { x: dx / length, y: dy / length, z: dz / length };
  const horizontal = Math.hypot(axis.x, axis.y);
  const u =
    horizontal > 1e-6
      ? { x: -axis.y / horizontal, y: axis.x / horizontal, z: 0 }
      : { x: 1, y: 0, z: 0 };
  const v = {
    x: axis.y * u.z - axis.z * u.y,
    y: axis.z * u.x - axis.x * u.z,
    z: axis.x * u.y - axis.y * u.x,
  };
  const normal = (angle: number) => ({
    x: u.x * Math.cos(angle) + v.x * Math.sin(angle),
    y: u.y * Math.cos(angle) + v.y * Math.sin(angle),
    z: u.z * Math.cos(angle) + v.z * Math.sin(angle),
  });
  const ring = (at: Vertex) =>
    Array.from({ length: sides }, (_, i) => {
      const n = normal((i * Math.PI * 2) / sides);
      return { x: at.x + n.x * radius, y: at.y + n.y * radius, z: at.z + n.z * radius };
    });
  const start = ring(a),
    end = ring(b);
  const faces: { points: Vertex[]; n: Vertex }[] = [];
  for (let i = 0; i < sides; i++)
    faces.push({
      points: [start[i], start[(i + 1) % sides], end[(i + 1) % sides], end[i]],
      n: normal(((i + 0.5) * Math.PI * 2) / sides),
    });
  faces.push(
    { points: start, n: { x: -axis.x, y: -axis.y, z: -axis.z } },
    { points: end, n: axis }
  );
  const depth = (points: Vertex[]) =>
    points.reduce((s, q) => s + q.x + q.y + q.z, 0) / points.length;
  for (const face of faces
    .filter(f => f.n.x + f.n.y + f.n.z > 0)
    .sort((a, b) => depth(a.points) - depth(b.points)))
    p.polygon(
      face.points.map(q => project(q, q.z)),
      shade(color, -20 - 12 * face.n.x + 12 * face.n.y + 33 * face.n.z)
    );
}

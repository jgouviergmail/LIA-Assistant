/** Source-UV coverage, computed once so the fringe cannot duplicate the solid body. */
import type { VolumeMask, VolumeMesh } from './volume-geometry';

type Point = { x: number; y: number };
const edge = (a: Point, b: Point, p: Point) =>
  (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x);

function coverTriangle(points: readonly Point[], mask: VolumeMask, covered: Uint8Array) {
  const [a, b, c] = points;
  const area = edge(a, b, c);
  if (Math.abs(area) < 0.00000001) return;
  const sign = Math.sign(area),
    minX = Math.max(0, Math.ceil(Math.min(a.x, b.x, c.x) - 0.5)),
    maxX = Math.min(mask.width - 1, Math.floor(Math.max(a.x, b.x, c.x) - 0.5)),
    minY = Math.max(0, Math.ceil(Math.min(a.y, b.y, c.y) - 0.5)),
    maxY = Math.min(mask.height - 1, Math.floor(Math.max(a.y, b.y, c.y) - 0.5));
  for (let y = minY; y <= maxY; y++)
    for (let x = minX; x <= maxX; x++) {
      const p = { x: x + 0.5, y: y + 0.5 };
      if (
        edge(a, b, p) * sign >= -0.00000001 &&
        edge(b, c, p) * sign >= -0.00000001 &&
        edge(c, a, p) * sign >= -0.00000001
      )
        covered[y * mask.width + x] = 1;
    }
}

/** Keep soft source shadows and every opaque pixel missing from the physical hull. */
export function volumeFringeAlpha(mesh: VolumeMesh, mask: VolumeMask): Uint8Array {
  const covered = new Uint8Array(mask.width * mask.height);
  for (let triangle = 0; triangle < mesh.indices.length; triangle += 3) {
    const indices = mesh.indices.subarray(triangle, triangle + 3);
    // A rear or side must not conceal a missing piece of the frontal artwork.
    if (
      indices.some(index => mesh.vertices[index * 8 + 2] < 0 || mesh.vertices[index * 8 + 5] > 1.5)
    )
      continue;
    const points = [...indices].map(index => ({
      x: mesh.vertices[index * 8 + 6] * mask.width,
      y: mesh.vertices[index * 8 + 7] * mask.height,
    }));
    coverTriangle(points, mask, covered);
  }
  return mask.alpha.map((value, index) => (value >= 180 && covered[index] ? 0 : value));
}

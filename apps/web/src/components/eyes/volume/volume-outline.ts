/** Physical alpha contour: soft source shadows never become opaque side walls. */
import {
  volumeDepth,
  type VolumeMask,
  type VolumeMesh,
  type VolumeProfile,
} from './volume-geometry';
import { smoothSurfaceNormals } from './volume-normals';
type Sample = { u: number; v: number; alpha: number };
const SOLID = 180;
function alpha(mask: VolumeMask, u: number, v: number) {
  const x = Math.max(0, Math.min(mask.width - 1, u * mask.width - 0.5)),
    y = Math.max(0, Math.min(mask.height - 1, v * mask.height - 0.5));
  const col = Math.floor(x),
    row = Math.floor(y),
    fx = x - col,
    fy = y - row;
  const at = (cx: number, cy: number) =>
    mask.alpha[Math.min(mask.height - 1, cy) * mask.width + Math.min(mask.width - 1, cx)];
  return (
    (at(col, row) * (1 - fx) + at(col + 1, row) * fx) * (1 - fy) +
    (at(col, row + 1) * (1 - fx) + at(col + 1, row + 1) * fx) * fy
  );
}
function cellPeak(mask: VolumeMask, col: number, row: number, grid: number): Sample {
  let best: Sample = { u: (col + 0.5) / grid, v: (row + 0.5) / grid, alpha: 0 };
  for (
    let y = Math.floor((row / grid) * mask.height);
    y < Math.min(mask.height, Math.ceil(((row + 1) / grid) * mask.height));
    y++
  )
    for (
      let x = Math.floor((col / grid) * mask.width);
      x < Math.min(mask.width, Math.ceil(((col + 1) / grid) * mask.width));
      x++
    )
      if (mask.alpha[y * mask.width + x] > best.alpha)
        best = {
          u: Math.max((col + 0.001) / grid, Math.min((col + 0.999) / grid, (x + 0.5) / mask.width)),
          v: Math.max(
            (row + 0.001) / grid,
            Math.min((row + 0.999) / grid, (y + 0.5) / mask.height)
          ),
          alpha: mask.alpha[y * mask.width + x],
        };
  return best;
}
/** Locate the source's contour, rather than inventing a linear alpha ramp
 * across an entire mesh cell (several source pixels wide). */
function contourPoint(mask: VolumeMask, a: Sample, b: Sample): Sample {
  let low = 0,
    high = 1;
  for (let iteration = 0; iteration < 8; iteration++) {
    const t = (low + high) / 2;
    const solid = alpha(mask, a.u + (b.u - a.u) * t, a.v + (b.v - a.v) * t) >= SOLID;
    if (solid === a.alpha >= SOLID) low = t;
    else high = t;
  }
  const t = (low + high) / 2;
  return { u: a.u + (b.u - a.u) * t, v: a.v + (b.v - a.v) * t, alpha: SOLID };
}
function clipped(mask: VolumeMask, triangle: readonly Sample[]): Sample[] {
  const polygon: Sample[] = [];
  for (let i = 0; i < triangle.length; i++) {
    const a = triangle[i],
      b = triangle[(i + 1) % triangle.length];
    if (a.alpha >= SOLID) polygon.push(a);
    if (a.alpha >= SOLID === b.alpha >= SOLID) continue;
    polygon.push(contourPoint(mask, a, b));
  }
  const distinct = polygon.filter(
    (sample, index) => index === 0 || !samePoint(sample, polygon[index - 1])
  );
  if (distinct.length > 1 && samePoint(distinct[0], distinct[distinct.length - 1])) distinct.pop();
  return distinct;
}
function samePoint(a: Sample, b: Sample) {
  return Math.abs(a.u - b.u) < 0.00000001 && Math.abs(a.v - b.v) < 0.00000001;
}
function opaqueUv(mask: VolumeMask, u: number, v: number): [number, number] {
  const cx = Math.floor(u * mask.width),
    cy = Math.floor(v * mask.height);
  for (let radius = 0; radius <= 16; radius++)
    for (let y = cy - radius; y <= cy + radius; y++)
      for (let x = cx - radius; x <= cx + radius; x++) {
        if (x < 0 || y < 0 || x >= mask.width || y >= mask.height) continue;
        if (mask.alpha[y * mask.width + x] >= 240)
          return [(x + 0.5) / mask.width, (y + 0.5) / mask.height];
      }
  return [u, v];
}
function cellTriangles(mask: VolumeMask, col: number, row: number, grid: number) {
  const corners = [
    [col, row],
    [col + 1, row],
    [col + 1, row + 1],
    [col, row + 1],
  ].map(([x, y]) => ({ u: x / grid, v: y / grid, alpha: alpha(mask, x / grid, y / grid) }));
  if (corners.some(sample => sample.alpha >= SOLID))
    return [
      [corners[0], corners[1], corners[2]],
      [corners[0], corners[2], corners[3]],
    ];
  // An isolated opaque crest can fall between all four grid corners.
  // Only that cell needs an extra point; regular sides retain straight edges.
  const peak = cellPeak(mask, col, row, grid);
  if (peak.alpha < SOLID) return [];
  return corners.map((corner, index) => [corner, corners[(index + 1) % 4], peak]);
}
function frontSurface(profile: VolumeProfile, mask: VolumeMask, grid: number) {
  const vertices: number[] = [],
    indices: number[] = [],
    mapped = new Map<string, number>();
  const vertexIndex = (sample: Sample) => {
    const key = `${sample.u.toFixed(7)},${sample.v.toFixed(7)}`;
    const existing = mapped.get(key);
    if (existing !== undefined) return existing;
    const x = (sample.u - 0.5) * 2.6 * profile.scale,
      y = (sample.v - 0.5) * 2.6 * profile.scale;
    const index = vertices.length / 8;
    vertices.push(
      x,
      y,
      profile.alphaDistance && sample.alpha === SOLID ? 0 : volumeDepth(profile, x, y),
      0,
      0,
      1,
      sample.u,
      sample.v
    );
    mapped.set(key, index);
    return index;
  };
  for (let row = 0; row < grid; row++)
    for (let col = 0; col < grid; col++) {
      for (const triangle of cellTriangles(mask, col, row, grid)) {
        const polygon = clipped(mask, triangle);
        for (let j = 1; j < polygon.length - 1; j++)
          indices.push(
            vertexIndex(polygon[0]),
            vertexIndex(polygon[j]),
            vertexIndex(polygon[j + 1])
          );
      }
    }
  return { vertices, indices };
}
function boundary(indices: readonly number[]) {
  const edges = new Map<string, { a: number; b: number; count: number }>();
  for (let i = 0; i < indices.length; i += 3)
    for (let e = 0; e < 3; e++) {
      const a = indices[i + e],
        b = indices[i + ((e + 1) % 3)],
        key = a < b ? `${a}:${b}` : `${b}:${a}`;
      const entry = edges.get(key);
      if (entry) entry.count++;
      else edges.set(key, { a, b, count: 1 });
    }
  return [...edges.values()].filter(edge => edge.count === 1);
}
/** The joined contour follows the source tangent, independent of thin triangles. */
function contourNormals(
  vertices: number[],
  edges: readonly { a: number; b: number }[],
  mask: VolumeMask
) {
  const contour = new Set(edges.flatMap(({ a, b }) => [a, b]));
  for (const index of contour) {
    const offset = index * 8,
      u = vertices[offset + 6],
      v = vertices[offset + 7];
    const nx =
        (alpha(mask, u - 0.5 / mask.width, v) - alpha(mask, u + 0.5 / mask.width, v)) * mask.width,
      ny =
        (alpha(mask, u, v - 0.5 / mask.height) - alpha(mask, u, v + 0.5 / mask.height)) *
        mask.height,
      length = Math.hypot(nx, ny);
    // An image-frame edge can have no alpha gradient; retain the hull normal.
    if (length === 0) continue;
    vertices[offset + 3] = nx / length;
    vertices[offset + 4] = ny / length;
    vertices[offset + 5] = 0;
  }
}
/** Reflect the rear with outward winding, keeping the joined contour welded. */
function rearSurface(
  front: { vertices: number[]; indices: number[] },
  vertices: number[],
  indices: number[]
) {
  const back: number[] = [];
  for (let i = 0; i < front.vertices.length; i += 8) {
    if (front.vertices[i + 2] === 0) {
      back.push(i / 8);
      continue;
    }
    back.push(vertices.length / 8);
    vertices.push(
      front.vertices[i],
      front.vertices[i + 1],
      -front.vertices[i + 2],
      front.vertices[i + 3],
      front.vertices[i + 4],
      -front.vertices[i + 5],
      front.vertices[i + 6],
      front.vertices[i + 7]
    );
  }
  for (let i = 0; i < front.indices.length; i += 3)
    indices.push(back[front.indices[i]], back[front.indices[i + 2]], back[front.indices[i + 1]]);
  return back;
}
export function alphaOutlineMesh(profile: VolumeProfile, mask: VolumeMask, grid = 32): VolumeMesh {
  const front = frontSurface(profile, mask, grid);
  const edges = boundary(front.indices);
  if (profile.alphaDistance)
    for (const { a, b } of edges) {
      front.vertices[a * 8 + 2] = 0;
      front.vertices[b * 8 + 2] = 0;
    }
  if (profile.alphaDistance) removeFlatCaps(front);
  // The monitor keeps its hard casing edges; organic contours share normals
  // across the front and rear after the whole hull has been assembled.
  if (!profile.alphaDistance) smoothSurfaceNormals(front.vertices, front.indices);
  const vertices = [...front.vertices],
    indices = [...front.indices],
    back = rearSurface(front, vertices, indices);
  for (const { a, b } of edges) {
    if (back[a] === a && back[b] === b) continue;
    const start = vertices.length / 8,
      dx = front.vertices[b * 8] - front.vertices[a * 8],
      dy = front.vertices[b * 8 + 1] - front.vertices[a * 8 + 1],
      len = Math.hypot(dx, dy) || 1;
    const [u, v] = opaqueUv(
      mask,
      (front.vertices[a * 8 + 6] + front.vertices[b * 8 + 6]) / 2,
      (front.vertices[a * 8 + 7] + front.vertices[b * 8 + 7]) / 2
    );
    for (const index of [a, b, back[b], back[a]])
      vertices.push(...vertices.slice(index * 8, index * 8 + 3), dy / len, -dx / len, 0, u, v);
    indices.push(start, start + 1, start + 2, start, start + 2, start + 3);
  }
  if (profile.alphaDistance) {
    smoothSurfaceNormals(vertices, indices);
    contourNormals(vertices, edges, mask);
  }
  if (vertices.length / 8 > 5000 && grid > 16) return alphaOutlineMesh(profile, mask, grid - 4);
  return { vertices: new Float32Array(vertices), indices: new Uint16Array(indices) };
}
/** A triangle wholly on the joined boundary encloses no volume; do not duplicate that sheet. */
function removeFlatCaps(front: { vertices: number[]; indices: number[] }) {
  const triangles: number[] = [];
  for (let i = 0; i < front.indices.length; i += 3) {
    const a = front.indices[i],
      b = front.indices[i + 1],
      c = front.indices[i + 2];
    if (
      front.vertices[a * 8 + 2] === 0 &&
      front.vertices[b * 8 + 2] === 0 &&
      front.vertices[c * 8 + 2] === 0
    )
      continue;
    triangles.push(a, b, c);
  }
  front.indices = triangles;
}

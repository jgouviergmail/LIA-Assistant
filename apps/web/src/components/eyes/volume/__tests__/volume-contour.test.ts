import { describe, expect, it } from 'vitest';
import { bodySurfaceProfile } from '../volume-distance';
import {
  visibleVolumeMesh,
  volumeProfile,
  type VolumeMask,
  type VolumeMesh,
  type VolumeProfile,
} from '../volume-geometry';

const WIDTH = 192;
const CENTRE = { x: 96.3, y: 91.7 };
const RADIUS = 56.75;

/** The alpha=180 contour is known independently of the meshing algorithm.
 * A fractional centre/radius keeps it away from both pixel and mesh grids. */
function smoothPortrait(): { profile: VolumeProfile; mask: VolumeMask } {
  const alpha = new Uint8Array(WIDTH * WIDTH);
  for (let y = 0; y < WIDTH; y++)
    for (let x = 0; x < WIDTH; x++) {
      const distance = Math.hypot(x + 0.5 - CENTRE.x, y + 0.5 - CENTRE.y);
      alpha[y * WIDTH + x] = Math.max(0, Math.min(255, Math.round(180 + (RADIUS - distance) * 96)));
    }
  const mask = { width: WIDTH, height: WIDTH, alpha };
  const base = volumeProfile('spirit', 'female');
  const profile = bodySurfaceProfile(
    {
      ...base,
      // One smooth lobe: no intentional corners, intersecting anatomy or
      // discontinuous max of two surfaces can explain a lighting seam here.
      lobes: [{ x: 0, y: 0, rx: 1.5, ry: 1.5, depth: 0.55 }],
    },
    mask
  );
  return { profile, mask };
}

function point(mesh: VolumeMesh, index: number) {
  const offset = index * 8;
  return {
    x: mesh.vertices[offset],
    y: mesh.vertices[offset + 1],
    z: mesh.vertices[offset + 2],
  };
}

describe('the physical contour and lighting describe the final surface', () => {
  it('locates every joined contour vertex within one source pixel of the real opaque contour', () => {
    const { profile, mask } = smoothPortrait();
    const mesh = visibleVolumeMesh(profile, mask);
    const boundary = [...new Set(mesh.indices)].filter(index => point(mesh, index).z === 0);
    expect(boundary.length).toBeGreaterThan(40);
    const errors = boundary.map(index => {
      const vertex = point(mesh, index);
      const x = (vertex.x / (2.6 * profile.scale) + 0.5) * WIDTH;
      const y = (vertex.y / (2.6 * profile.scale) + 0.5) * WIDTH;
      return Math.abs(Math.hypot(x - CENTRE.x, y - CENTRE.y) - RADIUS);
    });
    expect(Math.max(...errors)).toBeLessThanOrEqual(1);
  });

  it('aligns interior normals with the complete hull after contour vertices are moved', () => {
    const { profile, mask } = smoothPortrait();
    const mesh = visibleVolumeMesh(profile, mask);
    // Summed cross products integrate the actual incident tangent planes.
    // This oracle reads only final positions, never volumeDepth derivatives.
    const normals = new Float64Array(mesh.vertices.length);
    for (let offset = 0; offset < mesh.indices.length; offset += 3) {
      const indices = [...mesh.indices.slice(offset, offset + 3)];
      const [a, b, c] = indices.map(index => point(mesh, index));
      const ab = { x: b.x - a.x, y: b.y - a.y, z: b.z - a.z };
      const ac = { x: c.x - a.x, y: c.y - a.y, z: c.z - a.z };
      const cross = [
        ab.y * ac.z - ab.z * ac.y,
        ab.z * ac.x - ab.x * ac.z,
        ab.x * ac.y - ab.y * ac.x,
      ];
      for (const index of indices)
        for (let axis = 0; axis < 3; axis++) normals[index * 8 + axis] += cross[axis];
    }
    const cosines: number[] = [];
    for (const index of new Set(mesh.indices)) {
      const offset = index * 8;
      // At the joined edge, the independent alpha tangent is checked below.
      // Interior lighting must still follow the complete physical hull.
      if (mesh.vertices[offset + 2] === 0) continue;
      const length = Math.hypot(normals[offset], normals[offset + 1], normals[offset + 2]);
      if (length < 0.00000001) continue;
      const stored = mesh.vertices.slice(offset + 3, offset + 6);
      expect(Math.hypot(...stored)).toBeCloseTo(1, 5);
      const cosine = stored.reduce((sum, value, axis) => sum + value * normals[offset + axis], 0);
      cosines.push(cosine / length);
    }
    expect(cosines.length).toBeGreaterThan(100);
    // Eight degrees allows smooth interpolation, while rejecting normals
    // belonging to the unmodified analytical surface rather than this mesh.
    expect(Math.min(...cosines)).toBeGreaterThanOrEqual(Math.cos((8 * Math.PI) / 180));
  });

  it('joins front and rear with radial contour normals instead of an illuminated frontal cap', () => {
    const { profile, mask } = smoothPortrait();
    const mesh = visibleVolumeMesh(profile, mask);
    const boundary = [...new Set(mesh.indices)].filter(index => point(mesh, index).z === 0);
    expect(boundary.length).toBeGreaterThan(40);
    for (const index of boundary) {
      const position = point(mesh, index);
      const offset = index * 8;
      const nx = mesh.vertices[offset + 3];
      const ny = mesh.vertices[offset + 4];
      const nz = mesh.vertices[offset + 5];
      expect(Math.abs(nz)).toBeLessThan(0.00001);
      expect(Math.hypot(nx, ny, nz)).toBeCloseTo(1, 5);
      const sourceX = (position.x / (2.6 * profile.scale) + 0.5) * WIDTH - CENTRE.x;
      const sourceY = (position.y / (2.6 * profile.scale) + 0.5) * WIDTH - CENTRE.y;
      expect((nx * sourceX + ny * sourceY) / Math.hypot(sourceX, sourceY)).toBeGreaterThan(0.98);
    }
  });

  it('retains a finite closed hull within the existing vertex and index budgets', () => {
    const { profile, mask } = smoothPortrait();
    const mesh = visibleVolumeMesh(profile, mask, 64);
    const edges = new Map<string, number>();
    for (let offset = 0; offset < mesh.indices.length; offset += 3)
      for (let edge = 0; edge < 3; edge++) {
        const a = mesh.indices[offset + edge];
        const b = mesh.indices[offset + ((edge + 1) % 3)];
        const key = a < b ? `${a}:${b}` : `${b}:${a}`;
        edges.set(key, (edges.get(key) ?? 0) + 1);
      }
    expect([...mesh.vertices].every(Number.isFinite)).toBe(true);
    expect(mesh.vertices.length / 8).toBeLessThanOrEqual(5000);
    expect(mesh.indices.length).toBeLessThan(65536);
    expect([...edges.values()].every(count => count === 2)).toBe(true);
  });
});

import { describe, expect, it } from 'vitest';
import {
  VOLUME_CHARACTERS,
  volumeProfile,
  volumePose,
  volumeMesh,
  projectVolumeSurface,
  rotateVolumePoint,
  visibleVolumeMesh,
  volumeDepth,
} from '../volume-geometry';
import { restChannelValues } from '../../rig/channels';
import { clothMesh } from '../cloth-geometry';
import { volumeFaceContour } from '../volume-mask';

describe('structured body relief is closed 3D geometry, not a turning poster', () => {
  it('keeps the monitor straight physical edges straight instead of cutting a repeating peak fan into them', () => {
    const width = 192,
      alpha = new Uint8Array(width * width);
    for (let y = 28; y < 169; y++) for (let x = 35; x < 156; x++) alpha[y * width + x] = 255;
    const mesh = visibleVolumeMesh(volumeProfile('monitor', 'male'), {
      width,
      height: width,
      alpha,
    });
    const left: number[] = [];
    for (let i = 0; i < mesh.vertices.length; i += 8) {
      const [x, y, , , , nz] = mesh.vertices.slice(i, i + 6);
      if (nz === 0 && x < -0.65 && Math.abs(y) < 0.6) left.push(x);
    }
    expect(left.length).toBeGreaterThan(8);
    expect(Math.max(...left) - Math.min(...left)).toBeLessThan(0.000001);
    expect(mesh.vertices.length / 8).toBeLessThanOrEqual(5000);
  });
  it('closes the visible alpha island with opaque side walls, not the unrelated square frame', () => {
    const width = 192,
      alpha = new Uint8Array(width * width);
    for (let y = 25; y < 165; y++) for (let x = 35; x < 156; x++) alpha[y * width + x] = 255;
    // Physical crown stays; a diffuse shadow island must not become opaque geometry.
    alpha[2 * width + 100] = 200;
    alpha[2 * width + 15] = 32;
    const profile = volumeProfile('oscar', 'female');
    const mesh = visibleVolumeMesh(profile, { width, height: width, alpha });
    const key = (index: number) =>
      [...mesh.vertices.slice(index * 8, index * 8 + 3)].map(value => value.toFixed(5)).join(',');
    const edges = new Map<string, number>();
    let wallCount = 0,
      crown = false;
    for (let i = 0; i < mesh.indices.length; i += 3)
      for (let e = 0; e < 3; e++) {
        const a = key(mesh.indices[i + e]),
          b = key(mesh.indices[i + ((e + 1) % 3)]);
        const edge = a < b ? `${a}|${b}` : `${b}|${a}`;
        edges.set(edge, (edges.get(edge) ?? 0) + 1);
      }
    for (const index of mesh.indices) {
      const i = index * 8;
      crown ||= mesh.vertices[i + 1] < -1.4;
      if (mesh.vertices[i + 5] !== 0) continue;
      wallCount++;
      const u = mesh.vertices[i + 6],
        v = mesh.vertices[i + 7];
      expect(alpha[Math.floor(v * width) * width + Math.floor(u * width)]).toBeGreaterThanOrEqual(
        180
      );
      expect(Math.abs(mesh.vertices[i])).toBeLessThan(1.1);
    }
    expect(crown).toBe(true);
    expect(wallCount).toBeGreaterThan(0);
    expect([...edges.values()].every(count => count === 2)).toBe(true);
    expect(mesh.vertices.length / 8).toBeLessThanOrEqual(5000);
    expect(mesh.indices.length).toBeLessThan(65536);
  });

  it.each(VOLUME_CHARACTERS)(
    'registers the authored %s front scarf outside its torso with a bounded conforming mesh',
    character => {
      for (const variant of ['male', 'female'] as const) {
        const profile = volumeProfile(character, variant),
          mesh = clothMesh(profile.collar, profile);
        const width = profile.collar.radiusX * 2.2;
        expect(mesh.vertices.length / 8).toBeLessThanOrEqual(1024);
        for (let i = 0; i < mesh.vertices.length; i += 8) {
          const [x, y, z, nx, ny, nz, u, v] = mesh.vertices.slice(i, i + 8);
          expect(u).toBeGreaterThanOrEqual(0);
          expect(u).toBeLessThanOrEqual(1);
          expect(v).toBeGreaterThanOrEqual(0);
          expect(v).toBeLessThanOrEqual(1);
          expect(x).toBeCloseTo((u - 0.5) * width, 5);
          expect(y).toBeCloseTo(profile.collar.centerY + (v - 0.54) * width, 5);
          expect(z).toBeGreaterThanOrEqual(volumeDepth(profile, x, y) + 0.0249);
          expect(Math.hypot(nx, ny, nz)).toBeCloseTo(1, 5);
        }
        expect(profile.collar.radiusX).toBeLessThan(1.4);
      }
      const female = volumeProfile(character, 'female').collar.radiusX,
        male = volumeProfile(character, 'male').collar.radiusX;
      if (character === 'monitor') expect(female).toBe(male);
      else expect(female).toBeLessThan(male);
    }
  );

  it('uses a bounded alpha contour even at an image edge without wrapping into an adjacent row', () => {
    const alpha = new Uint8Array(192 * 192).fill(255),
      profile = volumeProfile('orbit', 'female');
    const contour = volumeFaceContour({ width: 192, height: 192, alpha }, profile, 0);
    expect(contour).toHaveLength(64);
    expect(contour.every(p => Math.abs(p.x) < 1.469 && Math.abs(p.y) < 1.469)).toBe(true);
  });
  it.each(VOLUME_CHARACTERS)(
    'retains front UV registration and closes %s with real front/back thickness',
    character => {
      const profile = volumeProfile(character, 'female');
      const mesh = volumeMesh(profile);
      expect(profile.lobes.length).toBeGreaterThanOrEqual(4);
      expect(profile.lobes.length).toBeLessThanOrEqual(8);
      const edges = new Map<string, number>();
      for (let i = 0; i < mesh.indices.length; i += 3)
        for (let e = 0; e < 3; e++) {
          const a = mesh.indices[i + e],
            b = mesh.indices[i + ((e + 1) % 3)];
          const key = a < b ? `${a}:${b}` : `${b}:${a}`;
          edges.set(key, (edges.get(key) ?? 0) + 1);
        }
      expect([...edges.values()].every(count => count === 2)).toBe(true);
      let thickness = 0;
      for (let i = 0; i < mesh.vertices.length; i += 8) {
        const [x, y, z] = mesh.vertices.slice(i, i + 3);
        thickness = Math.max(thickness, Math.abs(z));
        const point = rotateVolumePoint({ x, y, z }, { yaw: 0, pitch: 0 });
        expect(point.x).toBeCloseTo((mesh.vertices[i + 6] - 0.5) * 2.6 * profile.scale, 5);
        expect(point.y).toBeCloseTo((mesh.vertices[i + 7] - 0.5) * 2.6 * profile.scale, 5);
      }
      expect(thickness).toBeGreaterThan(0.15);
      expect(mesh.vertices.length).toBeLessThan(12_000);
    }
  );

  it('projects near and far sides differently and moves an attached face along its real tangent', () => {
    const profile = volumeProfile('orbit', 'male');
    const pose = { yaw: 0.3, pitch: 0.1 };
    const front = projectVolumeSurface(profile, { x: 0, y: 0 }, pose);
    const poster = rotateVolumePoint({ x: 0, y: 0, z: 0 }, pose);
    expect(front.x - poster.x).toBeGreaterThan(0.1);
    expect(front.a).not.toBe(1);
    expect(front.d).not.toBe(1);
    const left = projectVolumeSurface(profile, { x: -0.3, y: 0 }, pose);
    const right = projectVolumeSurface(profile, { x: 0.3, y: 0 }, pose);
    expect(left.a).not.toBeCloseTo(right.a, 3);
    expect(projectVolumeSurface(profile, { x: -0.3, y: 0 }, { yaw: 0, pitch: 0 })).toMatchObject({
      x: -0.3,
      y: 0,
      a: 1,
      b: 0,
      c: 0,
      d: 1,
    });
  });

  it('uses the current rig pose and keeps malformed inputs finite', () => {
    const values = { ...restChannelValues(), headYaw: Infinity, headPitch: NaN };
    expect(volumePose(values, 'monitor')).toEqual({ yaw: 0, pitch: 0 });
    const transformed = projectVolumeSurface(
      volumeProfile('oscar', 'female'),
      { x: 0, y: -0.4 },
      volumePose({ ...values, headYaw: 1, headPitch: -1 }, 'oscar')
    );
    expect(Object.values(transformed).every(Number.isFinite)).toBe(true);
  });
});

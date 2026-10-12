import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { companionBodyAsset } from '@/components/spirit/companion-catalogue';
import { bodySurfaceProfile } from '../volume-distance';
import {
  volumeDepth,
  volumeProfile,
  visibleVolumeMesh,
  rotateVolumePoint,
} from '../volume-geometry';
import { releaseNativeContext } from '../context-lifetime';
import portraitFixture from './fixtures/spirit-v2-alpha.json';

function realPortrait(variant: 'female' | 'male') {
  const portrait = portraitFixture.portraits[variant];
  expect(portrait.asset).toBe(companionBodyAsset('spirit', variant));
  const bytes = readFileSync(join(process.cwd(), 'public', portrait.asset));
  expect(createHash('sha256').update(bytes).digest('hex')).toBe(portrait.sha256);
  expect([portraitFixture.width, portraitFixture.height]).toEqual([192, 192]);
  expect(portraitFixture.thresholds).toEqual({ physical: 180, opaque: 240 });
  const flags = new Uint8Array(portraitFixture.width * portraitFixture.height);
  let offset = 0;
  for (const run of portrait.runs.split(' ')) {
    const [length, value] = run.split(':').map(Number);
    expect(length).toBeGreaterThan(0);
    expect([0, 1, 3]).toContain(value);
    flags.fill(value, offset, offset + length);
    offset += length;
  }
  expect(offset).toBe(flags.length);
  const alpha = Uint8Array.from(flags, value => (value & 1 ? 255 : 0));
  return { flags, mask: { width: portraitFixture.width, height: portraitFixture.height, alpha } };
}

/** A source-space disk, independent of the runtime chamfer distance transform.
 * Ten pixels exclude the thin silhouette taper and preserve the real torso. */
function innerTorso(flags: Uint8Array, width: number, height: number) {
  const disk: [number, number][] = [];
  for (let dy = -10; dy <= 10; dy++)
    for (let dx = -10; dx <= 10; dx++) if (dx * dx + dy * dy <= 100) disk.push([dx, dy]);
  const points: { u: number; v: number }[] = [];
  for (let y = Math.ceil(height * 0.24); y < height * 0.86; y++)
    for (let x = Math.ceil(width * 0.2); x < width * 0.8; x++) {
      // Alpha≥240 selects the opaque body; alpha≥180 defines its physical
      // silhouette. Soft artwork/shadows cannot turn into a false flatness.
      if (!(flags[y * width + x] & 2)) continue;
      if (disk.every(([dx, dy]) => flags[(y + dy) * width + x + dx] & 1))
        points.push({ u: (x + 0.5) / width, v: (y + 0.5) / height });
    }
  return points;
}

function mask() {
  const alpha = new Uint8Array(192 * 192);
  for (let y = 24; y < 169; y++) for (let x = 30; x < 162; x++) alpha[y * 192 + x] = 255;
  return { width: 192, height: 192, alpha };
}
describe('a closed inflated surface shares the original silhouette rather than cloning its edge', () => {
  it.each(['female', 'male'] as const)(
    'retains rounded %s torso relief throughout the real v2 opaque interior',
    variant => {
      const { flags, mask } = realPortrait(variant);
      const profile = bodySurfaceProfile(volumeProfile('spirit', variant), mask);
      const points = innerTorso(flags, mask.width, mask.height);
      expect(points.length).toBeGreaterThan(5000);
      const depths = points.map(({ u, v }) =>
        volumeDepth(profile, (u - 0.5) * 2.6 * profile.scale, (v - 0.5) * 2.6 * profile.scale)
      );
      // A registration mismatch leaves a large interior at the .018em
      // fallback plane even though the source portrait is smoothly rounded.
      expect(Math.min(...depths)).toBeGreaterThan(0.018);
    }
  );
  it('tapers thickness smoothly only near the physical contour and retains inner anatomy', () => {
    const base = volumeProfile('spirit', 'female'),
      profile = bodySurfaceProfile(base, mask());
    expect(volumeDepth(profile, 0, 0)).toBeCloseTo(volumeDepth(base, 0, 0), 8);
    const edgeX = (29.5 / 192 - 0.5) * 2.6 * profile.scale;
    expect(volumeDepth(profile, edgeX, 0)).toBe(0);
    const near = volumeDepth(profile, edgeX + 0.015, 0),
      inside = volumeDepth(profile, edgeX + 0.14, 0);
    expect(near).toBeLessThan(inside * 0.2);
    expect(near).toBeGreaterThanOrEqual(0);
    expect(volumeDepth(profile, edgeX - 0.01, 0)).toBe(0);
    const monitor = volumeProfile('monitor', 'male');
    expect(bodySurfaceProfile(monitor, mask())).toBe(monitor);
  });
  it('joins both surfaces on exactly the same rotated contour, without an opaque rim or detached back image', () => {
    const profile = bodySurfaceProfile(volumeProfile('spirit', 'female'), mask()),
      mesh = visibleVolumeMesh(profile, mask());
    const positions = new Map<string, number>();
    let boundary = 0;
    for (let i = 0; i < mesh.vertices.length; i += 8) {
      const [nx, ny, nz] = mesh.vertices.slice(i + 3, i + 6);
      expect(Math.hypot(nx, ny, nz)).toBeCloseTo(1, 5);
      if (mesh.vertices[i + 2] > 0) expect(nz).toBeGreaterThan(0);
      if (mesh.vertices[i + 2] < 0) expect(nz).toBeLessThan(0);
      if (mesh.vertices[i + 2] !== 0) continue;
      boundary++;
      expect(Math.abs(nz)).toBeLessThan(0.00001);
      const p = { x: mesh.vertices[i], y: mesh.vertices[i + 1], z: 0 };
      expect(nx * p.x + ny * p.y).toBeGreaterThan(0);
      const projected = rotateVolumePoint(p, { yaw: 0.36, pitch: 0.18 });
      expect(projected).toEqual(rotateVolumePoint({ ...p, z: -0 }, { yaw: 0.36, pitch: 0.18 }));
      const key = `${p.x},${p.y}`;
      positions.set(key, (positions.get(key) ?? 0) + 1);
    }
    expect(boundary).toBeGreaterThan(20);
    expect([...positions.values()].every(count => count === 1)).toBe(true);
    const edges = new Map<string, number>();
    for (let i = 0; i < mesh.indices.length; i += 3)
      for (let j = 0; j < 3; j++) {
        const a = mesh.indices[i + j],
          b = mesh.indices[i + ((j + 1) % 3)],
          key = a < b ? `${a}:${b}` : `${b}:${a}`;
        edges.set(key, (edges.get(key) ?? 0) + 1);
      }
    expect([...edges.values()].every(count => count === 2)).toBe(true);
    expect(mesh.vertices.length / 8).toBeLessThanOrEqual(5000);
  });
  it('releases a permanently detached native context once when requested and tolerates unavailable extensions', () => {
    const loseContext = vi.fn(),
      getExtension = vi.fn(() => ({ loseContext }));
    releaseNativeContext({ getExtension });
    expect(getExtension).toHaveBeenCalledWith('WEBGL_lose_context');
    expect(loseContext).toHaveBeenCalledOnce();
    expect(() => releaseNativeContext(null)).not.toThrow();
    expect(() => releaseNativeContext({ getExtension: () => null })).not.toThrow();
    expect(() =>
      releaseNativeContext({
        getExtension: () => {
          throw Error('lost');
        },
      })
    ).not.toThrow();
  });
});

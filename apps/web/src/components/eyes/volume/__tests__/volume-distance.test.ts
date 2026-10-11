import { describe, expect, it, vi } from 'vitest';
import { bodySurfaceProfile } from '../volume-distance';
import {
  volumeDepth,
  volumeProfile,
  visibleVolumeMesh,
  rotateVolumePoint,
} from '../volume-geometry';
import { releaseNativeContext } from '../context-lifetime';
function mask() {
  const alpha = new Uint8Array(192 * 192);
  for (let y = 24; y < 169; y++) for (let x = 30; x < 162; x++) alpha[y * 192 + x] = 255;
  return { width: 192, height: 192, alpha };
}
describe('a closed inflated surface shares the original silhouette rather than cloning its edge', () => {
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
      expect(mesh.vertices[i + 5]).not.toBe(0);
      if (mesh.vertices[i + 2] !== 0) continue;
      boundary++;
      const p = { x: mesh.vertices[i], y: mesh.vertices[i + 1], z: 0 };
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

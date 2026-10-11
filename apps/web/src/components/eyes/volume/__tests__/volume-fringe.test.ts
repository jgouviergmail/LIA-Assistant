import { describe, expect, it } from 'vitest';
import { withSoftFringe } from '../volume-fringe';
import { bodySurfaceProfile } from '../volume-distance';
import { visibleVolumeMesh, volumeProfile, rotateVolumePoint } from '../volume-geometry';
import { createMeshGpu } from '../mesh-gpu';
import { smileyClothGraphics } from '../../__tests__/smiley-cloth-graphics';
describe('soft source alpha never becomes an opaque physical rear or side', () => {
  it('preserves opaque source pixels missing from a sampled edge using the same depth-tested material film', () => {
    const profile = volumeProfile('oscar', 'female'),
      physical = { vertices: new Float32Array(), indices: new Uint16Array() },
      mesh = withSoftFringe(physical, profile),
      gl = smileyClothGraphics();
    const gpu = createMeshGpu(document.createElement('canvas'), gl, mesh);
    const fragment = gl.shaderSource.mock.calls
      .map(([, source]) => source)
      .find(source => source.includes('texture2D'))!;
    // Coverage may have any original alpha: coarse hull coverage must not erase an opaque hair pixel.
    expect(fragment).not.toMatch(/tex\.a\s*>=\s*180/);
    expect(fragment).toContain('tex.rgb*tex.a,tex.a');
    expect(mesh.vertices.length / 8).toBe(4);
    expect(mesh.indices.length).toBe(6);
    gpu?.dispose();
  });
  it('never promotes an interpolated zero rear normal to an opaque rim', () => {
    const alpha = new Uint8Array(192 * 192);
    for (let y = 30; y < 160; y++) for (let x = 30; x < 160; x++) alpha[y * 192 + x] = 255;
    const profile = bodySurfaceProfile(volumeProfile('oscar', 'female'), {
        width: 192,
        height: 192,
        alpha,
      }),
      mesh = visibleVolumeMesh(profile, { width: 192, height: 192, alpha });
    let mixedRear = false;
    for (let i = 0; i < mesh.indices.length; i += 3) {
      const normals = [...mesh.indices.slice(i, i + 3)].map(index => mesh.vertices[index * 8 + 5]);
      mixedRear ||= Math.min(...normals) < 0 && Math.max(...normals) > 0;
    }
    // Shared contour vertices have a front normal, so the rear interpolation crosses zero.
    expect(mixedRear).toBe(true);
    const gl = smileyClothGraphics(),
      gpu = createMeshGpu(document.createElement('canvas'), gl, mesh);
    const sources = gl.shaderSource.mock.calls.map(([, source]) => source),
      vertex = sources.find(source => source.includes('attribute'))!,
      fragment = sources.find(source => source.includes('texture2D'))!;
    expect(vertex).toMatch(/abs\(a_normal\.z\)/);
    expect(fragment).not.toMatch(/abs\(v_original\.z\)/);
    gpu?.dispose();
  });
  it('preserves the complete closed hull and adds only two planar source-fringe triangles', () => {
    const alpha = new Uint8Array(192 * 192);
    for (let y = 30; y < 160; y++) for (let x = 30; x < 160; x++) alpha[y * 192 + x] = 255;
    const mask = { width: 192, height: 192, alpha },
      profile = bodySurfaceProfile(volumeProfile('spirit', 'female'), mask);
    const physical = visibleVolumeMesh(profile, mask),
      combined = withSoftFringe(physical, profile);
    expect(combined.indices.slice(0, physical.indices.length)).toEqual(physical.indices);
    expect(combined.vertices.slice(0, physical.vertices.length)).toEqual(physical.vertices);
    expect(combined.vertices.length - physical.vertices.length).toBe(32);
    expect(combined.indices.length - physical.indices.length).toBe(6);
    for (let i = physical.vertices.length; i < combined.vertices.length; i += 8) {
      expect(combined.vertices[i + 2]).toBe(0);
      expect(combined.vertices[i + 5]).toBe(2);
      expect(combined.vertices[i]).toBeCloseTo(
        (combined.vertices[i + 6] - 0.5) * 2.6 * profile.scale,
        6
      );
      expect(combined.vertices[i + 1]).toBeCloseTo(
        (combined.vertices[i + 7] - 0.5) * 2.6 * profile.scale,
        6
      );
      const p = { x: combined.vertices[i], y: combined.vertices[i + 1], z: 0 };
      expect(rotateVolumePoint(p, { yaw: 0.36, pitch: 0.1 })).toEqual(
        rotateVolumePoint({ ...p, z: -0 }, { yaw: 0.36, pitch: 0.1 })
      );
    }
  });
});

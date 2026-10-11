/** Complete source coverage is a thin core film, depth-tested behind the closed relief. */
import type { VolumeMesh, VolumeProfile } from './volume-geometry';
export function withSoftFringe(mesh: VolumeMesh, profile: VolumeProfile): VolumeMesh {
  const start = mesh.vertices.length / 8,
    half = 1.3 * profile.scale;
  const vertices = new Float32Array(mesh.vertices.length + 32);
  vertices.set(mesh.vertices);
  // Normal.z=2 is a material flag, not another anatomical surface or rear.
  vertices.set(
    [
      -half,
      -half,
      0,
      0,
      0,
      2,
      0,
      0,
      half,
      -half,
      0,
      0,
      0,
      2,
      1,
      0,
      half,
      half,
      0,
      0,
      0,
      2,
      1,
      1,
      -half,
      half,
      0,
      0,
      0,
      2,
      0,
      1,
    ],
    mesh.vertices.length
  );
  const indices = new Uint16Array(mesh.indices.length + 6);
  indices.set(mesh.indices);
  indices.set([start, start + 1, start + 2, start, start + 2, start + 3], mesh.indices.length);
  return { vertices, indices };
}

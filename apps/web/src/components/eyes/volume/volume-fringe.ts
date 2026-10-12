/** Source shadows and unmeshed details remain behind the closed relief. */
import type { VolumeMask, VolumeMesh, VolumeProfile } from './volume-geometry';
import { volumeFringeAlpha } from './volume-coverage';

/** A bounded alpha texture shares the material's existing source read. */
export function volumeFringeMask(mesh: VolumeMesh, mask: VolumeMask): HTMLCanvasElement | null {
  try {
    const canvas = document.createElement('canvas');
    canvas.width = mask.width;
    canvas.height = mask.height;
    const context = canvas.getContext('2d');
    if (!context) return null;
    const pixels = context.createImageData(mask.width, mask.height),
      alpha = volumeFringeAlpha(mesh, mask);
    for (let index = 0; index < alpha.length; index++) pixels.data[index * 4 + 3] = alpha[index];
    context.putImageData(pixels, 0, 0);
    return canvas;
  } catch {
    return null;
  }
}
export function withSoftFringe(mesh: VolumeMesh, profile: VolumeProfile): VolumeMesh {
  const start = mesh.vertices.length / 8,
    half = 1.3 * profile.scale;
  const vertices = new Float32Array(mesh.vertices.length + 32);
  vertices.set(mesh.vertices);
  // Normal.z=2 flags the masked fringe, not another anatomical surface or rear.
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

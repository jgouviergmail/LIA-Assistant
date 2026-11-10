/** Source shadows and unmeshed details remain behind the closed relief. */
import type { VolumeMask, VolumeMesh, VolumeProfile } from './volume-geometry';
import { volumeFringeAlpha } from './volume-coverage';
import { limbProfile } from './limb-profiles';

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

/** Refine moving source regions only; rigid tiles retain their four original corners. */
export function withSoftFringe(mesh: VolumeMesh, profile: VolumeProfile): VolumeMesh {
  const chains = limbProfile(profile.character, profile.variant);
  const tiles = chains.length ? 8 : 1;
  const vertices = Array.from(mesh.vertices),
    indices = Array.from(mesh.indices);
  const points = new Map<string, number>();
  const point = (u: number, v: number): number => {
    const key = `${u},${v}`;
    const present = points.get(key);
    if (present !== undefined) return present;
    const index = vertices.length / 8;
    // Normal.z=2 flags the masked fringe before deformation, never an anatomical normal.
    vertices.push(
      (u - 0.5) * 2.6 * profile.scale,
      (v - 0.5) * 2.6 * profile.scale,
      0,
      0,
      0,
      2,
      u,
      v
    );
    points.set(key, index);
    return index;
  };
  for (let row = 0; row < tiles; row++)
    for (let col = 0; col < tiles; col++) {
      const moving = chains.some(
        ({ region: [x0, y0, x1, y1] }) =>
          x0 <= (col + 1) / tiles &&
          x1 >= col / tiles &&
          y0 <= (row + 1) / tiles &&
          y1 >= row / tiles
      );
      const divisions = moving ? 8 : 1;
      for (let y = 0; y < divisions; y++)
        for (let x = 0; x < divisions; x++) {
          const left = (col + x / divisions) / tiles,
            right = (col + (x + 1) / divisions) / tiles;
          const top = (row + y / divisions) / tiles,
            bottom = (row + (y + 1) / divisions) / tiles;
          const a = point(left, top),
            b = point(right, top),
            c = point(right, bottom),
            d = point(left, bottom);
          indices.push(a, b, c, a, c, d);
        }
    }
  return { vertices: new Float32Array(vertices), indices: new Uint16Array(indices) };
}

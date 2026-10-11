/** One source-resolution chamfer transform closes inflated silhouettes at their physical contour. */
import type { VolumeMask, VolumeProfile } from './volume-geometry';

export function bodySurfaceProfile(profile: VolumeProfile, mask: VolumeMask): VolumeProfile {
  if (profile.character === 'monitor') return profile;
  const { width, height, alpha } = mask,
    values = new Float32Array(width * height);
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++)
      values[y * width + x] =
        alpha[y * width + x] >= 180 ? Math.min(x + 1, y + 1, width - x, height - y) : 0;
  distancePass(values, width, height, 1);
  distancePass(values, width, height, -1);
  return { ...profile, alphaDistance: { width, height, values } };
}
function distancePass(values: Float32Array, width: number, height: number, step: 1 | -1) {
  const start = step === 1 ? 0 : width * height - 1;
  for (let i = start; i >= 0 && i < values.length; i += step) {
    if (values[i] === 0) continue;
    const x = i % width,
      y = Math.floor(i / width);
    const sample = (dx: number, dy: number, cost: number) => {
      const nx = x + dx,
        ny = y + dy;
      if (nx >= 0 && ny >= 0 && nx < width && ny < height)
        values[i] = Math.min(values[i], values[ny * width + nx] + cost);
    };
    sample(-step, 0, 1);
    sample(0, -step, 1);
    sample(-step, -step, Math.SQRT2);
    sample(step, -step, Math.SQRT2);
  }
}
export function silhouetteDepth(profile: VolumeProfile, x: number, y: number) {
  const field = profile.alphaDistance;
  if (!field) return 1;
  const px = (x / (2.6 * profile.scale) + 0.5) * field.width - 0.5,
    py = (y / (2.6 * profile.scale) + 0.5) * field.height - 0.5;
  const col = Math.floor(px),
    row = Math.floor(py),
    fx = px - col,
    fy = py - row;
  const at = (cx: number, cy: number) =>
    cx >= 0 && cy >= 0 && cx < field.width && cy < field.height
      ? field.values[cy * field.width + cx]
      : 0;
  const pixels =
    (at(col, row) * (1 - fx) + at(col + 1, row) * fx) * (1 - fy) +
    (at(col, row + 1) * (1 - fx) + at(col + 1, row + 1) * fx) * fy;
  if (pixels < 0.0000001) return 0;
  const t = Math.max(0, Math.min(1, (pixels * 2.6 * profile.scale) / field.width / 0.12));
  return t * t * (3 - 2 * t);
}

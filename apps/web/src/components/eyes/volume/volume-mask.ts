/** One bounded CPU alpha read at asset load. No GPU readback or per-frame image work. */
import type { VolumeMask, VolumeProfile } from './volume-geometry';
export function readVolumeMask(image: HTMLImageElement): VolumeMask | null {
  try {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 192;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) return null;
    context.drawImage(image, 0, 0, 192, 192);
    const rgba = context.getImageData(0, 0, 192, 192).data,
      alpha = new Uint8Array(192 * 192);
    for (let i = 0; i < alpha.length; i++) alpha[i] = rgba[i * 4 + 3];
    return { width: 192, height: 192, alpha };
  } catch {
    return null;
  }
}

export function volumeFaceContour(mask: VolumeMask, profile: VolumeProfile, centerY: number) {
  const point = (x: number, y: number) =>
    x >= 0 && y >= 0 && x < mask.width && y < mask.height
      ? (mask.alpha[Math.floor(y) * mask.width + Math.floor(x)] ?? 0)
      : 0;
  const cx = mask.width / 2,
    cy = (centerY / (2.6 * profile.scale) + 0.5) * mask.height;
  const contour: { x: number; y: number }[] = [];
  for (let index = 0; index < 64; index++) {
    const angle = (index / 64) * Math.PI * 2,
      dx = Math.cos(angle),
      dy = Math.sin(angle);
    let distance = 0;
    while (distance < 192 && point(cx + dx * distance, cy + dy * distance) > 200) distance++;
    distance = Math.max(0, distance - 2);
    contour.push({
      x: ((dx * distance) / mask.width) * 2.6 * profile.scale,
      y: centerY + ((dy * distance) / mask.height) * 2.6 * profile.scale,
    });
  }
  return contour;
}

/** Authored voxel hairstyles rotate with the same orthographic mesh as the face. */
import type { AvatarAppearance } from '../avatar-catalogue';
import type { ActorMesh } from './actor-mesh';
import { shade } from './painter';

export function personHair(
  mesh: ActorMesh,
  style: AvatarAppearance['hair'],
  color: string,
  bob: number
): void {
  const box = (x: number, y: number, z: number, w: number, d: number, h: number, tint = color) =>
    mesh.box(x, y, z + bob, w, d, h, tint);
  if (style === 'bald') return;
  box(0.17, 0.15, 1.82, 0.72, 0.71, 0.16);
  if (style === 'mohawk') {
    box(0.42, 0.18, 1.96, 0.22, 0.63, 0.23, shade(color, 12));
    box(0.47, 0.12, 2.07, 0.12, 0.28, 0.14);
    return;
  }
  box(0.17, 0.15, 1.29, 0.72, 0.14, 0.57);
  box(0.17, 0.15, 1.52, 0.11, 0.68, 0.32);
  box(0.2, 0.71, 1.72, 0.3, 0.15, 0.13, shade(color, 8));
  if (style === 'short') return;
  if (style === 'curly') {
    for (const [x, y, z] of [
      [0.14, 0.12, 1.7],
      [0.44, 0.1, 1.86],
      [0.71, 0.16, 1.76],
      [0.12, 0.49, 1.85],
      [0.66, 0.55, 1.87],
      [0.38, 0.73, 1.8],
    ])
      box(x, y, z, 0.24, 0.23, 0.22, shade(color, x < 0.4 ? 6 : -5));
    return;
  }
  if (style === 'ponytail') {
    box(0.37, -0.02, 1.45, 0.32, 0.24, 0.36);
    box(0.4, -0.09, 1.1, 0.27, 0.25, 0.42, shade(color, -9));
    box(0.39, -0.03, 1.48, 0.3, 0.24, 0.06, '#d8ad65');
    return;
  }
  box(0.14, 0.12, 1.05, 0.16, 0.65, 0.78);
  box(0.76, 0.12, 1.05, 0.16, 0.59, 0.78, shade(color, -6));
  box(0.17, 0.09, 0.98, 0.72, 0.2, 0.7);
  box(0.18, 0.1, 0.94, 0.22, 0.22, 0.14, shade(color, 7));
  box(0.65, 0.1, 0.94, 0.22, 0.22, 0.14);
}

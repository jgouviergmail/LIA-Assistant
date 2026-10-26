/** Small explicit accessories; never inferred from the native account profile. */
import type { AvatarAppearance } from '../avatar-catalogue';
import type { ActorMesh } from './actor-mesh';
import { shade } from './painter';
export function personHeadwear(
  mesh: ActorMesh,
  style: AvatarAppearance['headwear'],
  color: string,
  bob: number
): void {
  if (style === 'none') return;
  if (style === 'cap') {
    mesh.box(0.14, 0.12, 1.88 + bob, 0.78, 0.75, 0.2, color);
    mesh.box(0.2, 0.8, 1.88 + bob, 0.66, 0.35, 0.065, shade(color, -12));
    mesh.front(0.46, 0.872, 1.96 + bob, 0.15, 0.07, '#f4e9cc');
    return;
  }
  if (style === 'beanie') {
    mesh.box(0.13, 0.1, 1.84 + bob, 0.8, 0.79, 0.24, color);
    mesh.box(0.11, 0.08, 1.82 + bob, 0.84, 0.83, 0.08, shade(color, -20));
    mesh.box(0.43, 0.36, 2.08 + bob, 0.2, 0.24, 0.1, shade(color, 12));
    return;
  }
  mesh.box(0.02, 0.02, 1.88 + bob, 1.02, 0.98, 0.065, shade(color, -15));
  mesh.box(0.23, 0.22, 1.94 + bob, 0.6, 0.58, 0.3, color);
  mesh.box(0.23, 0.22, 1.98 + bob, 0.6, 0.58, 0.06, '#c2a16b');
}
export function personGlasses(mesh: ActorMesh, bob: number): void {
  for (const x of [0.28, 0.61]) {
    mesh.front(x, 0.855, 1.51 + bob, 0.18, 0.13, '#28323d');
    mesh.front(x + 0.025, 0.855, 1.535 + bob, 0.13, 0.08, '#c2e1e5');
    mesh.front(x + 0.065, 0.855, 1.54 + bob, 0.045, 0.05, '#28323d');
  }
  mesh.front(0.46, 0.855, 1.57 + bob, 0.15, 0.025, '#28323d');
}
export function avatarLabelOffset(appearance?: AvatarAppearance): number {
  if (appearance?.headwear === 'hat') return 96;
  return appearance?.hair === 'mohawk' ? 94 : 83;
}

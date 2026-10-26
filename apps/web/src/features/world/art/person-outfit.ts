import type { AvatarAppearance } from '../avatar-catalogue';
import type { ActorMesh } from './actor-mesh';
import { shade } from './painter';
export function personOutfit(
  mesh: ActorMesh,
  style: AvatarAppearance['outfit'],
  cloth: string,
  bob: number,
  sitting: boolean
): void {
  const front = mesh.front.bind(mesh);
  front(0.39, 0.768, 0.98 + bob, 0.23, 0.18, '#f2eadd');
  if (style === 'suit') {
    for (const x of [0.26, 0.64]) front(x, 0.775, 0.91 + bob, 0.11, 0.25, shade(cloth, 20));
    front(0.48, 0.78, 0.83 + bob, 0.065, 0.29, '#ae3941');
    front(0.47, 0.78, 1.1 + bob, 0.085, 0.055, '#d66161');
    front(0.65, 0.78, 0.86 + bob, 0.1, 0.06, '#e9d9bc');
    front(0.47, 0.78, 0.7 + bob, 0.03, 0.03, '#d4bc87');
    return;
  }
  if (style === 'dress') {
    // Layered skirt remains below the hands and follows the seated thighs.
    const z = sitting ? 0.48 + bob : 0.25 + bob;
    mesh.box(0.12, 0.2, z, 0.79, sitting ? 0.76 : 0.61, sitting ? 0.2 : 0.4, cloth);
    mesh.box(0.08, 0.18, z, 0.87, sitting ? 0.8 : 0.65, 0.09, shade(cloth, 9));
    front(0.24, 0.765, 0.75 + bob, 0.54, 0.065, shade(cloth, -24));
    front(0.46, 0.775, 0.8 + bob, 0.1, 0.12, '#dfba70');
    return;
  }
  front(0.26, 0.775, 1.04 + bob, 0.15, 0.13, shade(cloth, 19));
  front(0.61, 0.775, 1.04 + bob, 0.15, 0.13, shade(cloth, 19));
  front(0.51, 0.78, 0.64 + bob, 0.018, 0.33, shade(cloth, -18));
  front(0.65, 0.78, 0.86 + bob, 0.1, 0.09, shade(cloth, 12));
  for (const z of [0.72, 0.86]) front(0.47, 0.785, z + bob, 0.025, 0.025, '#d6c8a8');
}

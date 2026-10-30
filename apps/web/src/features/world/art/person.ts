/** Original voxel people, with explicitly chosen finite appearance. */
import type { Tone } from '../types';
import { shade, type Sprite } from './painter';
import { ActorMesh } from './actor-mesh';
import {
  AVATAR_COLORS,
  AVATAR_SKINS,
  DEFAULT_AVATAR,
  type AvatarAppearance,
} from '../avatar-catalogue';
import { personHair } from './person-hair';
import { personOutfit } from './person-outfit';
import { personHeadwear, personGlasses } from './person-accessories';
import { ACCENTS } from './palette';
import { personArms } from './person-arms';
import type { PersonInteraction } from '../decor-presentation';

function personLegs(
  mesh: ActorMesh,
  stride: number,
  pose?: import('../pose-slots').PoseSlot | null
): void {
  const box = mesh.box.bind(mesh),
    front = mesh.front.bind(mesh);
  for (const [x, step] of [
    [0.27, stride],
    [0.57, -stride],
  ]) {
    if (pose?.kind === 'sit') {
      box(x, 0.35, pose.elevation - 0.1, 0.2, 0.65, 0.22, '#4d5a61');
      box(x, 0.84, Math.max(0.08, pose.elevation - 0.55), 0.2, 0.22, 0.46, '#4d5a61');
      box(x - 0.025, 0.8, Math.max(0.03, pose.elevation - 0.6), 0.25, 0.4, 0.12, '#34444b');
      continue;
    }
    const lift = Math.max(0, step / 0.11) ** 2 * 0.045;
    box(x, 0.32 + step, 0.08 + lift, 0.2, 0.29, 0.47 - lift, '#4d5a61');
    box(x - 0.025, 0.31 + step, 0.03 + lift, 0.25, 0.4, 0.12, '#34444b');
    box(x - 0.025, 0.31 + step, 0.02 + lift, 0.25, 0.4, 0.035, '#b0ad98');
    front(x, 0.615 + step, 0.17 + lift, 0.2, 0.025, '#64716e');
  }
}
function visibleHair(chosen: AvatarAppearance): AvatarAppearance['hair'] {
  return chosen.headwear !== 'none' && chosen.hair === 'mohawk' ? 'short' : chosen.hair;
}
export function paintPerson(
  facing: number,
  phase: number,
  ratio: number,
  tone: Tone,
  heading = facing * 2,
  pose?: import('../pose-slots').PoseSlot | null,
  appearance?: AvatarAppearance,
  interaction?: PersonInteraction
): Sprite {
  const mesh = new ActorMesh(heading, pose?.kind === 'lie' ? pose.elevation : undefined);
  const stride = pose ? 0 : Math.sin((phase * Math.PI) / 4) * 0.11;
  const bob = pose?.kind === 'sit' ? pose.elevation - 0.53 : (stride / 0.11) ** 2 * 0.012;
  const chosen = appearance ?? DEFAULT_AVATAR;
  const cloth = appearance ? AVATAR_COLORS[chosen.outfit_color] : ACCENTS[tone],
    skin = AVATAR_SKINS[chosen.skin],
    hair = AVATAR_COLORS[chosen.hair_color];
  const box = mesh.box.bind(mesh);
  const front = mesh.front.bind(mesh);
  personLegs(mesh, stride, pose);
  box(0.19, 0.23, 0.53 + bob, 0.64, 0.53, 0.65, cloth);
  front(0.22, 0.765, 0.55 + bob, 0.58, 0.035, shade(cloth, -20));
  personArms(mesh, stride * 0.72, bob, cloth, skin, interaction);
  personOutfit(mesh, chosen.outfit, cloth, bob, pose?.kind === 'sit');
  box(0.4, 0.38, 1.17 + bob, 0.23, 0.28, 0.12, skin);
  box(0.18, 0.17, 1.28 + bob, 0.7, 0.68, 0.6, skin);
  personHair(mesh, visibleHair(chosen), hair, bob);
  for (const x of [0.32, 0.63]) {
    front(x, 0.855, 1.54 + bob, 0.09, 0.085, '#f4f3e9');
    front(x + 0.025, 0.86, 1.55 + bob, 0.045, 0.065, '#272b31');
  }
  front(0.46, 0.86, 1.37 + bob, 0.16, 0.025, '#8a6254');
  front(0.27, 0.856, 1.45 + bob, 0.1, 0.035, shade(skin, -12));
  if (chosen.glasses) personGlasses(mesh, bob);
  personHeadwear(mesh, chosen.headwear, AVATAR_COLORS[chosen.headwear_color], bob);
  return mesh.sprite(ratio);
}

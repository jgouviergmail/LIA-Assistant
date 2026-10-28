import {
  WORKOUT_BODY_Y,
  BAR_CHEST_Y,
  BAR_RACK_Y,
  BAR_LIFT,
  type PersonInteraction,
} from '../decor-presentation';
import type { ActorMesh } from './actor-mesh';
import { shade } from './painter';

export function personArms(
  mesh: ActorMesh,
  stride: number,
  bob: number,
  cloth: string,
  skin: string,
  interaction?: PersonInteraction
): void {
  const box = mesh.box.bind(mesh);
  for (const [x, step] of [
    [0.02, -stride],
    [0.84, stride],
  ]) {
    if (interaction?.kind === 'fish') {
      box(x, 0.27, 0.86 + bob, 0.17, 0.24, 0.26, cloth);
      box(x > 0.5 ? 0.58 : x + 0.015, 0.43, 0.95 + bob, 0.38, 0.18, 0.14, skin);
      box(x > 0.5 ? 0.54 : 0.42, 0.57, 1 + bob, 0.14, 0.19, 0.14, skin);
      continue;
    }
    if (interaction?.kind === 'press') {
      const lift = interaction.lift * BAR_LIFT;
      const grip =
        WORKOUT_BODY_Y + 1 - (BAR_RACK_Y + (BAR_CHEST_Y - BAR_RACK_Y) * interaction.reach + 0.04);
      box(x, 0.38, 0.94, 0.17, 0.3, 0.25, cloth);
      box(
        x + 0.015,
        0.55,
        Math.min(1.02, grip),
        0.14,
        0.22 + lift,
        Math.abs(grip - 1.02) + 0.16,
        skin
      );
      box(x + 0.015, 0.76 + lift, grip - 0.07, 0.14, 0.14, 0.16, skin);
      continue;
    }
    if (interaction?.kind === 'coin' && x > 0.5) {
      const extend =
        interaction.phase < 0.18
          ? interaction.phase / 0.18
          : Math.max(0, 1 - (interaction.phase - 0.18) / 0.5);
      box(x, 0.27, 0.86 + bob, 0.17, 0.24, 0.26, cloth);
      box(x + 0.015, 0.38, 0.95 + bob, 0.14, 0.23 + extend * 0.3, 0.14, skin);
      box(x + 0.015, 0.5 + extend * 0.3, 0.98 + bob, 0.14, 0.14, 0.17, skin);
      continue;
    }
    box(x, 0.27 + step, 0.76 + bob, 0.17, 0.24, 0.36, cloth);
    box(x + 0.015, 0.29 + step, 0.57 + bob, 0.14, 0.21, 0.21, skin);
    box(x, 0.27 + step, 0.75 + bob, 0.17, 0.24, 0.055, shade(cloth, 18));
  }
}

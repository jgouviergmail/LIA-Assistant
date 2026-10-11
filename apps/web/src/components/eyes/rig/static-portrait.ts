/** Historical portraits paint once; they own no clock or live subscriptions. */
import { createRigWriter } from './apply';
import { createEyeRig, type RigPose } from './runtime';
import type { RigCharacterId } from './acting-profile';

export function bindStaticPortrait(
  element: HTMLElement,
  pose: RigPose,
  characterId?: RigCharacterId
) {
  const rig = createEyeRig({ initial: pose, characterId, reducedMotion: true });
  const writer = createRigWriter(element);
  const wake = () => {
    rig.settle();
    writer.write(rig.values());
  };
  wake();
  return { rig, wake, dispose: () => writer.dispose() };
}

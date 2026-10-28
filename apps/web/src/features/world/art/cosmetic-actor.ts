import type { Actor } from '../types';
import type { CosmeticFrame } from '../cosmetic-effects';
import { pressLift, pressReach, type PersonInteraction } from '../decor-presentation';
import { headingFromMotion } from './actor-direction';
function standingInteraction(
  frame: CosmeticFrame,
  reduced: boolean
): PersonInteraction | undefined {
  if (frame.action === 'pond')
    return { kind: 'fish', phase: reduced ? 0.5 : Math.round(frame.phase * 24) / 24 };
  return reduced ? undefined : { kind: 'coin', phase: Math.round(frame.phase * 24) / 24 };
}

export function cosmeticActor(
  actor: Actor,
  frames: ReadonlyMap<string, CosmeticFrame>,
  reduced: boolean
): { interaction?: PersonInteraction; heading: number } {
  const heading = actor.heading ?? actor.facing * 2;
  for (const frame of frames.values()) {
    if (frame.action === 'workout' && actor.pose?.prop === frame.id)
      return {
        heading,
        interaction: {
          kind: 'press',
          lift: reduced ? 0.5 : Math.round(pressLift(frame.phase) * 16) / 16,
          reach: reduced ? 1 : Math.round(pressReach(frame.phase) * 16) / 16,
        },
      };
    if (
      !['fountain', 'pond'].includes(frame.action) ||
      !frame.origin ||
      actor.pose ||
      actor.walking
    )
      continue;
    if (Math.hypot(frame.origin.x - actor.position.x, frame.origin.y - actor.position.y) > 0.3)
      continue;
    return {
      heading: headingFromMotion(
        { x: frame.point.x - actor.position.x, y: frame.point.y - actor.position.y },
        heading
      ),
      interaction: standingInteraction(frame, reduced),
    };
  }
  return { heading };
}

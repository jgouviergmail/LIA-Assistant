import { WORLD } from './definition';
import { authoredActivity, type SceneActivity } from './activity-catalogue';
import { compilePoseSlots } from './pose-slots';
export type { SceneActivity } from './activity-catalogue';

/** Objects and their seats share the same closed vocabulary, not a URL or a callback. */
const AUTHORED = new Map(
  WORLD.props.flatMap(prop => {
    const activity = authoredActivity(prop.activity ?? prop.key);
    return activity ? [[prop.id, activity] as const] : [];
  })
);
const SEATED = new Map(
  compilePoseSlots(WORLD).flatMap(slot => {
    const activity = AUTHORED.get(slot.prop);
    return activity ? [[slot.id, activity] as const] : [];
  })
);
export function sceneActivity(id: string): SceneActivity | null {
  return AUTHORED.get(id) ?? null;
}
export function seatActivity(id: string): SceneActivity | null {
  return SEATED.get(id) ?? null;
}

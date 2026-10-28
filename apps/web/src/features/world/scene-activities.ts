import { WORLD } from './definition';
import { authoredActivity, type SceneActivity } from './activity-catalogue';
import { seatContext } from './seat-context';
export type { SceneActivity } from './activity-catalogue';

/** Objects and their seats share the same closed vocabulary, not a URL or a callback. */
const AUTHORED = new Map(
  WORLD.props.flatMap(prop => {
    const activity = authoredActivity(prop.activity ?? prop.key);
    return activity ? [[prop.id, activity] as const] : [];
  })
);
export function sceneActivity(id: string): SceneActivity | null {
  return AUTHORED.get(id) ?? null;
}
export function seatActivity(id: string): SceneActivity | null {
  return seatContext(id)?.activity ?? null;
}

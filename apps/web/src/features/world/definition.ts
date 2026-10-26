import { MOVEMENT } from './movement';
import { HOUSE_GROUNDS, HOUSE_WALLS, HOUSE_ZONES } from './house-layout';
import { HOUSE_FURNITURE } from './house-furniture';
import { HOUSE_GARDEN } from './house-garden';
import type { GroundPatch, Point, WorldDefinition } from './types';

/** Site margin keeps a navigable tree belt around the authored building.
 * IDs and support references remain stable when the complete site is offset.
 */
export const SITE_OFFSET_X = 6;
export function onSite<T extends Point>(point: T): T {
  return { ...point, x: point.x + SITE_OFFSET_X };
}
/** One social house and nearby outdoor activities. Private data is never authored here. */
export const WORLD: WorldDefinition = {
  id: 'lia-campus',
  version: 13,
  movement: MOVEMENT,
  width: 74,
  height: 84,
  spawn: onSite({ x: 31.5, y: 33.5 }),
  bipSpawn: onSite({ x: 33.5, y: 33.5 }),
  patrol: [
    { x: 33.5, y: 31.5 },
    { x: 38.5, y: 27.5 },
    { x: 31.5, y: 20.5 },
    { x: 24.5, y: 31.5 },
  ].map(onSite),
  zones: HOUSE_ZONES.map(zone => ({ ...onSite(zone), arrival: onSite(zone.arrival) })),
  grounds: HOUSE_GROUNDS.map(onSite),
  props: [...HOUSE_WALLS, ...HOUSE_FURNITURE, ...HOUSE_GARDEN].map(onSite),
};

export function groundAt(world: WorldDefinition, x: number, y: number): GroundPatch['kind'] {
  for (let i = world.grounds.length - 1; i >= 0; i--) {
    const patch = world.grounds[i];
    if (x >= patch.x && y >= patch.y && x < patch.x + patch.width && y < patch.y + patch.height)
      return patch.kind;
  }
  return 'grass';
}

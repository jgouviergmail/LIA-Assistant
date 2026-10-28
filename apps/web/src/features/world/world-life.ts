/** Bounded cosmetic life; never participates in collisions, presence or private data. */
import type { Atmosphere } from './atmosphere';
import type { Quality, WorldDefinition, WorldProp } from './types';
import type { CosmeticTarget } from './cosmetic-interactions';
export interface AmbientAgent extends CosmeticTarget {
  readonly index: number;
}
/** Shared paint/pick positions. These targets never enter authored collision geometry. */
export function ambientLifeAt(
  world: WorldDefinition,
  atmosphere: Atmosphere,
  time: number,
  quality: Quality,
  reduced: boolean
): readonly AmbientAgent[] {
  const garden = world.zones.find(zone => zone.id === 'garden');
  if (!garden || !Number.isFinite(time)) return [];
  const budget = lifeBudget(atmosphere, quality, reduced);
  return [
    ...Array.from(
      { length: budget.birds },
      (_, index): AmbientAgent => ({
        id: 'ambient-bird-' + index,
        action: 'bird',
        index,
        point: {
          x: garden.x + garden.width / 2 + Math.sin(time * 0.09 + index) * 8,
          y: garden.y + 12 + Math.cos(time * 0.07 + index) * 6,
        },
        elevation: 4 + index * 0.4,
      })
    ),
    ...Array.from(
      { length: budget.butterflies },
      (_, index): AmbientAgent => ({
        id: 'ambient-butterfly-' + index,
        action: 'butterfly',
        index,
        point: {
          x: garden.x + 3 + index * 4 + Math.sin(time * 0.5 + index) * 0.7,
          y: garden.y + 7 + Math.cos(time * 0.4 + index) * 1.3,
        },
        elevation: 0.8 + Math.sin(time * 0.8 + index) * 0.2,
      })
    ),
  ];
}
export function lifeBudget(
  a: Atmosphere,
  q: Quality,
  reduced: boolean
): { birds: number; butterflies: number } {
  if (reduced || !['morning', 'noon', 'afternoon'].includes(a.phase))
    return { birds: 0, butterflies: 0 };
  return { birds: q === 'low' ? 1 : 3, butterflies: a.sunny ? (q === 'low' ? 1 : 4) : 0 };
}
export function catAt(world: WorldDefinition, time: number): WorldProp | null {
  const room = world.zones.find(z => z.id === 'divination');
  if (!room || !Number.isFinite(time)) return null;
  const points = [
    { x: 2.5, y: 4.5 },
    { x: 5.5, y: 4.5 },
    { x: 5.5, y: 9.5 },
    { x: 2.5, y: 9.5 },
  ];
  const distance = (Math.max(0, time) * 0.65) % 16,
    limits = [3, 5, 3, 5];
  let remaining = distance,
    index = 0;
  while (index < 3 && remaining >= limits[index]) remaining -= limits[index++];
  const a = points[index],
    b = points[(index + 1) % 4],
    t = remaining / limits[index];
  const facing = ([0, 1, 2, 3] as const)[index],
    width = facing % 2 === 0 ? 0.8 : 0.45,
    depth = facing % 2 === 0 ? 0.45 : 0.8;
  return {
    id: 'ambient-cat',
    kind: 'cat',
    x: room.x + a.x + (b.x - a.x) * t - width / 2,
    y: room.y + a.y + (b.y - a.y) * t - depth / 2,
    width,
    depth,
    height: 0.75,
    tone: 'violet',
    facing,
    blocking: false,
  };
}

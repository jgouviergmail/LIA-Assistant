/** Authored shared vocabulary, compiled into the server catalogue by the parity gate. */
import type { Facing } from './art/actor-direction';
import type { Point, WorldDefinition, WorldProp } from './types';
import { authoredActivity } from './activity-catalogue';
import { WORKOUT_BODY_Y } from './decor-presentation';
export interface PoseSlot {
  id: string;
  prop: string;
  kind: 'sit' | 'lie';
  position: Point;
  approach: Point;
  facing: Facing;
  elevation: number;
}
const SEATS = new Set<WorldProp['kind']>([
  'chair',
  'sofa',
  'bench',
  'toilet',
  'bed',
  'lounger',
  'weightbench',
]);
function approach(prop: WorldProp, position: Point, facing: Facing): Point {
  if (prop.kind === 'bed') return { x: Math.ceil(prop.x + prop.width) + 0.5, y: position.y };
  switch (facing) {
    case 0:
      return { x: Math.ceil(prop.x + prop.width) + 0.5, y: position.y };
    case 1:
      return { x: position.x, y: Math.ceil(prop.y + prop.depth) + 0.5 };
    case 2:
      return { x: Math.floor(prop.x) - 0.5, y: position.y };
    case 3:
      return { x: position.x, y: Math.floor(prop.y) - 0.5 };
  }
}
function workoutPosition(prop: WorldProp, facing: Facing): Point {
  if (facing === 0) return { x: prop.x + WORKOUT_BODY_Y, y: prop.y + prop.depth / 2 };
  if (facing === 2) return { x: prop.x + prop.width - WORKOUT_BODY_Y, y: prop.y + prop.depth / 2 };
  return {
    x: prop.x + prop.width / 2,
    y: prop.y + (facing === 1 ? WORKOUT_BODY_Y : prop.depth - WORKOUT_BODY_Y),
  };
}
export function compilePoseSlots(world: WorldDefinition): PoseSlot[] {
  return world.props.flatMap(prop => {
    if (!prop.key || !SEATS.has(prop.kind)) return [];
    if (prop.kind === 'weightbench' && authoredActivity(prop.activity ?? prop.key)) return [];
    const facing = prop.facing ?? 1;
    const horizontal = facing === 1 || facing === 3;
    const count = prop.kind === 'bench' ? 3 : prop.kind === 'sofa' ? 2 : 1;
    const lying = prop.kind === 'bed' || prop.kind === 'lounger' || prop.kind === 'weightbench';
    return Array.from({ length: count }, (_, i) => {
      const along = (i + 0.5) / count;
      const position =
        prop.kind === 'weightbench'
          ? workoutPosition(prop, facing)
          : {
              x: prop.x + prop.width * (horizontal ? along : 0.5),
              y: prop.y + prop.depth * (horizontal ? 0.5 : along),
            };
      return {
        id: prop.key + ':' + i,
        prop: prop.id,
        kind: lying ? ('lie' as const) : ('sit' as const),
        position,
        approach: approach(prop, position, facing),
        facing: prop.kind === 'bed' ? 1 : facing,
        elevation:
          prop.kind === 'weightbench'
            ? 0.87
            : prop.kind === 'chair'
              ? 0.665
              : prop.kind === 'sofa'
                ? 0.73
                : prop.kind === 'bench'
                  ? 0.62
                  : prop.kind === 'toilet'
                    ? 0.56
                    : 0.72,
      };
    });
  });
}

import type { Point, WorldProp } from './types';
import { authoredActivity } from './activity-catalogue';
import { hasDecorScreen } from './decor-presentation';
export const COSMETIC_ACTIONS = [
  'cat',
  'butterfly',
  'pond',
  'fountain',
  'plant',
  'billiards',
  'machine',
  'lamp',
  'screen',
  'workout',
] as const;
export type CosmeticActionId = (typeof COSMETIC_ACTIONS)[number] | 'bird';
export interface CosmeticTarget {
  readonly id: string;
  readonly action: CosmeticActionId;
  readonly point: Point;
  readonly elevation: number;
  readonly origin?: Point;
}
const PROP_ACTIONS: Partial<Record<WorldProp['kind'], CosmeticActionId>> = {
  cat: 'cat',
  pond: 'pond',
  fountain: 'fountain',
  plant: 'plant',
  planter: 'plant',
  billiards: 'billiards',
  machine: 'machine',
  lamp: 'lamp',
  tablelamp: 'lamp',
  display: 'screen',
  desk: 'screen',
  weightbench: 'workout',
};
export function cosmeticPropTarget(prop: WorldProp): CosmeticTarget | null {
  if (authoredActivity(prop.activity ?? prop.key)) return null;
  const action = PROP_ACTIONS[prop.kind];
  if (!action || (action === 'screen' && !hasDecorScreen(prop))) return null;
  return {
    id: prop.id,
    action,
    point: { x: prop.x + prop.width / 2, y: prop.y + prop.depth / 2 },
    elevation: action === 'pond' ? 0.12 : action === 'fountain' ? 0.3 : prop.height * 0.7,
  };
}
export function cosmeticActionForId(
  world: { props: readonly WorldProp[] },
  id: string
): CosmeticActionId | null {
  if (id === 'ambient-cat') return 'cat';
  if (/^ambient-butterfly-[0-3]$/.test(id)) return 'butterfly';
  const prop = world.props.find(item => item.id === id);
  return prop ? (cosmeticPropTarget(prop)?.action ?? null) : null;
}

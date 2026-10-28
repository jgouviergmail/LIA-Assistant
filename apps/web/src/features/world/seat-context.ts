/** Explicit authored relationships: no distance heuristic may assign a table. */
import { WORLD } from './definition';
import { authoredActivity, type SceneActivity } from './activity-catalogue';
import { compilePoseSlots } from './pose-slots';
import type { WorldDefinition, WorldProp } from './types';

export interface SeatContext {
  tableKey: string | null;
  activity: SceneActivity | null;
  dashboardEligible: boolean;
}
export function compileSeatContexts(world: WorldDefinition): ReadonlyMap<string, SeatContext> {
  const keyed = new Map<string, (typeof world.props)[number]>();
  for (const prop of world.props) {
    if (!prop.key) continue;
    if (keyed.has(prop.key)) throw new Error('duplicate_world_prop_key');
    keyed.set(prop.key, prop);
  }
  const result = new Map<string, SeatContext>();
  for (const slot of compilePoseSlots(world)) {
    const prop = world.props.find(item => item.id === slot.prop)!;
    if (prop.tableKey && keyed.get(prop.tableKey)?.kind !== 'table')
      throw new Error('invalid_seat_table');
    const table = prop.tableKey ? keyed.get(prop.tableKey) : undefined;
    const activity =
      authoredActivity(prop.activity ?? prop.key) ??
      authoredActivity(table?.activity ?? table?.key);
    result.set(slot.id, {
      tableKey: prop.tableKey ?? null,
      activity,
      dashboardEligible: dashboardEligible(prop, table, activity),
    });
  }
  return result;
}
function dashboardEligible(
  seat: WorldProp,
  table: WorldProp | undefined,
  activity: SceneActivity | null
): boolean {
  const canSit = seat.kind === 'chair' || seat.kind === 'sofa';
  return canSit && !!table && !activity;
}
const CONTEXTS = compileSeatContexts(WORLD);
export function seatContext(slot: string): SeatContext | null {
  return CONTEXTS.get(slot) ?? null;
}

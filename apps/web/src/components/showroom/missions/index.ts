/**
 * Ordered registry of the guided showroom missions.
 *
 * The canonical order is the picker order: the original orchestration
 * mission first, then one mission per differentiating mechanism. The id
 * list mirrors `SHOWROOM_MISSION_IDS` in `lib/product-telemetry` (and the
 * backend vocabulary) — completeness is guarded by fixtures.test.ts, so a
 * mission cannot exist without its two bounded per-mission funnel events.
 */

import { CONFIG_TOUR } from '@/components/showroom/missions/config-tour';
import { DAILY_BRIEFING } from '@/components/showroom/missions/daily-briefing';
import { MEMORY_DINNER } from '@/components/showroom/missions/memory-dinner';
import { OVERLOADED_MORNING } from '@/components/showroom/missions/overloaded-morning';
import { PHONE_BOOKING } from '@/components/showroom/missions/phone-booking';
import { PROACTIVE_ALERT } from '@/components/showroom/missions/proactive-alert';
import type { ShowroomMissionDefinition, ShowroomMissionId } from '@/components/showroom/types';

export const SHOWROOM_MISSIONS: readonly ShowroomMissionDefinition[] = [
  OVERLOADED_MORNING,
  PROACTIVE_ALERT,
  MEMORY_DINNER,
  PHONE_BOOKING,
  DAILY_BRIEFING,
  CONFIG_TOUR,
];

const BY_ID = new Map(SHOWROOM_MISSIONS.map(m => [m.id, m]));

/** Resolve a mission by id; throws on an unknown id (registry completeness). */
export function getShowroomMission(id: ShowroomMissionId): ShowroomMissionDefinition {
  const mission = BY_ID.get(id);
  if (!mission) throw new Error(`unknown showroom mission '${id}'`);
  return mission;
}

/**
 * The lights screen's model (ADR-369, Task 9.2): pure.
 *
 * What a lamp can do names its controls. A room's brightness is read from the
 * lights that are on (exact: the bridge is read whole). Rooms and lamps are
 * drawn in alphabetical order (owner request 2026-10-31).
 */
import type { WorkbenchLight, WorkbenchLights, WorkbenchRoom } from './types';

/** What a lamp can do, as its controls read. */
export type LightKind = 'color_and_white' | 'white_ambiance' | 'dimmable' | 'on_off';

/**
 * @param light - A lamp.
 * @returns What it can do.
 */
export function lightKind(light: WorkbenchLight): LightKind {
  if (light.supports_color) return 'color_and_white';
  if (light.mirek_min !== null) return 'white_ambiance';
  return light.brightness === null ? 'on_off' : 'dimmable';
}

/**
 * The folded section that holds a lamp's colour temperature and colour, named by
 * what the lamp can take (owner request 2026-10-31: folded until opened).
 *
 * @param light - A lamp.
 * @returns The section's title key, or null when the lamp takes neither.
 */
export function toneTitleKey(light: WorkbenchLight): string | null {
  const temperature = light.mirek_min !== null && light.mirek_max !== null;
  if (temperature && light.supports_color) return 'workbench.lights.tone';
  if (temperature) return 'workbench.lights.temperature';
  return light.supports_color ? 'workbench.lights.colour' : null;
}

/**
 * The bridge with its rooms and its lamps in alphabetical order, in the reader's
 * language: case and accents do not decide, and a number is read as a number
 * (« Lampe 2 » before « Lampe 10 »). The scenes keep the bridge's order.
 *
 * @param bridge - The bridge, as read.
 * @param language - The interface language the names are compared in.
 * @returns A new bridge; the one given is left as it was.
 */
export function inNameOrder(bridge: WorkbenchLights, language: string): WorkbenchLights {
  const collator = new Intl.Collator(language, { numeric: true });
  const byName = <T extends { name: string }>(items: readonly T[]): T[] =>
    [...items].sort((a, b) => collator.compare(a.name, b.name));
  return { ...bridge, rooms: byName(bridge.rooms), lights: byName(bridge.lights) };
}

/**
 * @param lightIds - A room's lights.
 * @param lights - Every light read.
 * @returns The mean brightness of its dimmable lights that are on, or null.
 */
export function roomBrightness(
  lightIds: readonly string[],
  lights: readonly WorkbenchLight[]
): number | null {
  const members = new Set(lightIds);
  const lit = lights.filter(item => members.has(item.id) && item.on && item.brightness !== null);
  if (lit.length === 0) return null;
  const total = lit.reduce((sum, item) => sum + (item.brightness ?? 0), 0);
  return Math.round(total / lit.length);
}

/** The pseudo-room of the lamps no room owns (`?room=other`). */
export const OTHER_LIGHTS = 'other';

/** What the lights screen shows open. */
export interface LightsSelection {
  /** The lamps no room owns. */
  orphans: WorkbenchLight[];
  /** The open room's id (`OTHER_LIGHTS` for the orphans), or null. */
  openId: string | null;
  /** The open room, or null (nothing open, or the orphans). */
  openRoom: WorkbenchRoom | null;
  /** The lamps of what is open. */
  openLights: WorkbenchLight[];
  /** Whether a detail is drawn at all. */
  detailOpen: boolean;
}

/**
 * @param bridge - The bridge, read whole.
 * @param asked - The room the URL names (`?room=`), or null.
 * @param desktop - Whether the room sits beside the list (from `lg`), where the
 *   first room — else the orphans — opens when none is asked.
 * @returns What is open.
 */
export function openSelection(
  bridge: WorkbenchLights,
  asked: string | null,
  desktop: boolean
): LightsSelection {
  const orphans = bridge.lights.filter(light => light.room_id === null);
  const first = bridge.rooms[0]?.id ?? (orphans.length > 0 ? OTHER_LIGHTS : null);
  const openId = asked ?? (desktop ? first : null);
  const openRoom = bridge.rooms.find(room => room.id === openId) ?? null;
  const members = new Set(openRoom?.light_ids ?? []);
  return {
    orphans,
    openId,
    openRoom,
    openLights:
      openId === OTHER_LIGHTS ? orphans : bridge.lights.filter(light => members.has(light.id)),
    detailOpen: openRoom !== null || openId === OTHER_LIGHTS,
  };
}

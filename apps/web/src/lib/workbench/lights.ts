/**
 * The lights screen's model (ADR-369, Task 9.2): pure.
 *
 * What a lamp can do names its controls. A room's brightness is read from the
 * lights that are on (exact: the bridge is read whole). Rooms and lamps are
 * drawn in alphabetical order (owner request 2026-10-31).
 */
import type { WorkbenchLight, WorkbenchLights, WorkbenchRoom, WorkbenchScene } from './types';

/** What a lamp can do, as its controls read. */
export type LightKind = 'color_and_white' | 'white_ambiance' | 'dimmable' | 'on_off';

/** What a lamp, or every lamp of a room, can take of a tone. */
export type ToneOffer = Pick<WorkbenchLight, 'supports_color' | 'mirek_min' | 'mirek_max'>;

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
 * Whether there is a folded section to open for a lamp's colour temperature and colour (owner
 * request 2026-10-31: folded until opened).
 *
 * @param offer - What a lamp or a room can take.
 * @returns Whether it takes either.
 */
export function offersTone(offer: ToneOffer): boolean {
  return offer.supports_color || (offer.mirek_min !== null && offer.mirek_max !== null);
}

/**
 * The bridge with its rooms, then its zones, and its lamps in alphabetical order, in
 * the reader's language: case and accents do not decide, and a number is read as a
 * number (« Lampe 2 » before « Lampe 10 »). The scenes keep the bridge's order.
 *
 * @param bridge - The bridge, as read.
 * @param language - The interface language the names are compared in.
 * @returns A new bridge; the one given is left as it was.
 */
export function inNameOrder(bridge: WorkbenchLights, language: string): WorkbenchLights {
  const collator = new Intl.Collator(language, { numeric: true });
  const byName = <T extends { name: string }>(items: readonly T[]): T[] =>
    [...items].sort((a, b) => collator.compare(a.name, b.name));
  const zones = bridge.rooms.filter(room => room.kind === 'zone');
  const rooms = bridge.rooms.filter(room => room.kind !== 'zone');
  return { ...bridge, rooms: [...byName(rooms), ...byName(zones)], lights: byName(bridge.lights) };
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

/**
 * @param lightIds - A room's lights.
 * @param lights - Every light read.
 * @returns The mean temperature of those that report one, or null.
 */
export function roomMirek(
  lightIds: readonly string[],
  lights: readonly WorkbenchLight[]
): number | null {
  const members = new Set(lightIds);
  const toned = lights.filter(item => members.has(item.id) && item.mirek !== null);
  if (toned.length === 0) return null;
  return Math.round(toned.reduce((sum, item) => sum + (item.mirek ?? 0), 0) / toned.length);
}

/**
 * @param lightIds - A room's lights.
 * @param lights - Every light read.
 * @returns The colour the first of them that shows one shows, or null.
 */
export function roomColour(
  lightIds: readonly string[],
  lights: readonly WorkbenchLight[]
): string | null {
  const members = new Set(lightIds);
  return lights.find(item => members.has(item.id) && item.color_hex)?.color_hex ?? null;
}

/**
 * @param lightIds - A room's lights.
 * @param lights - Every light read.
 * @returns How many of them the bridge says it cannot reach.
 */
/**
 * What is off stands apart from the page and from what is lit, which keeps the card's own material:
 * `--color-unlit` lies under the page in a light theme, and between the page and the card in a dark
 * one, so that nothing off ever outshines a lit tile.
 */
export const UNLIT_CARD = 'data-[lit=false]:bg-unlit';

/** The lamps that answer, then those the bridge says it cannot reach, each in its order. */
export function lampsByAnswer(lights: readonly WorkbenchLight[]): {
  answering: WorkbenchLight[];
  silent: WorkbenchLight[];
} {
  return {
    answering: lights.filter(lamp => lamp.reachable !== false),
    silent: lights.filter(lamp => lamp.reachable === false),
  };
}


/** The pseudo-room of the lamps no room owns (`?room=other`). */
export const OTHER_LIGHTS = 'other';

/**
 * @param bridge - The bridge.
 * @returns The scenes no room or zone holds.
 */
export function scenesOutsideRooms(bridge: WorkbenchLights): WorkbenchScene[] {
  const rooms = new Set(bridge.rooms.map(room => room.id));
  return bridge.scenes.filter(scene => scene.room_id === null || !rooms.has(scene.room_id));
}

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

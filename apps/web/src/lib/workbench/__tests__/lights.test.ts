/**
 * The lights screen's model (ADR-369, Task 9.2): what a lamp can do names its
 * controls, and a room's brightness is read from the lights that are on.
 */

import { describe, expect, it } from 'vitest';

import type { WorkbenchLight, WorkbenchLights, WorkbenchRoom } from '../types';
import {
  OTHER_LIGHTS,
  inNameOrder,
  lightKind,
  openSelection,
  roomBrightness,
  roomColour,
  roomMirek,
  lampsByAnswer,
  scenesOutsideRooms,
  toneTitleKey,
  unreachableCount,
} from '../lights';

const PLAIN_ROOM = {
  kind: 'room',
  supports_color: false,
  mirek_min: null,
  mirek_max: null,
} as const;
const STILL = { dynamic: false, playing: false };

function light(id: string, overrides: Partial<WorkbenchLight> = {}): WorkbenchLight {
  return {
    id,
    name: id,
    room_id: 'r1',
    on: true,
    brightness: 50,
    supports_color: false,
    color_hex: null,
    mirek: null,
    mirek_min: null,
    mirek_max: null,
    reachable: null,
    ...overrides,
  };
}

describe('a room and a zone', () => {
  const zone: WorkbenchRoom = {
    ...PLAIN_ROOM,
    kind: 'zone',
    id: 'z1',
    name: 'Aa',
    light_ids: [],
    on: false,
  };
  const room = { ...PLAIN_ROOM, id: 'r1', name: 'Zz', light_ids: [], on: false };

  it('draws the rooms first: a zone gathers lamps a room already holds', () => {
    const ordered = inNameOrder({ rooms: [zone, room], lights: [], scenes: [] }, 'en');

    expect(ordered.rooms.map(item => item.id)).toEqual(['r1', 'z1']);
  });

  it("keeps a zone's scenes with the zone", () => {
    const held = { id: 's1', name: 'Calm', room_id: 'z1', active: false, ...STILL };
    const lost = { id: 's2', name: 'Calm', room_id: 'gone', active: false, ...STILL };

    expect(
      scenesOutsideRooms({ rooms: [zone], lights: [], scenes: [held, lost] }).map(item => item.id)
    ).toEqual(['s2']);
  });

  it("names a room's tone by what its lamps take", () => {
    expect(toneTitleKey({ supports_color: true, mirek_min: 153, mirek_max: 500 })).toBe(
      'workbench.lights.tone'
    );
    expect(toneTitleKey({ supports_color: false, mirek_min: null, mirek_max: null })).toBeNull();
  });
});

describe('lampsByAnswer', () => {
  it('sets apart the lamps the bridge cannot reach, each group in its order', () => {
    const lights = [
      light('a', { reachable: false }),
      light('b', { reachable: true }),
      light('c', { reachable: null }),
      light('d', { reachable: false }),
    ];

    const { answering, silent } = lampsByAnswer(lights);

    expect(answering.map(lamp => lamp.id)).toEqual(['b', 'c']);
    expect(silent.map(lamp => lamp.id)).toEqual(['a', 'd']);
  });
});

describe('unreachableCount', () => {
  it('counts the lamps the bridge says it cannot reach, and no others', () => {
    const lights = [
      light('a', { reachable: false }),
      light('b', { reachable: true }),
      light('c', { reachable: null }),
      light('d', { reachable: false }),
    ];

    expect(unreachableCount(['a', 'b', 'c'], lights)).toBe(1);
  });
});

describe('roomColour', () => {
  it('reads the first lamp that shows one, whichever comes first in the room', () => {
    const lights = [light('a'), light('b', { color_hex: '#ff0000' })];

    expect(roomColour(['a', 'b'], lights)).toBe('#ff0000');
  });

  it('reads nothing from a lamp of another room', () => {
    expect(roomColour(['a'], [light('a'), light('b', { color_hex: '#ff0000' })])).toBeNull();
  });
});

describe('roomMirek', () => {
  it('reads the mean temperature of the lamps that have one', () => {
    const lights = [light('a', { mirek: 200 }), light('b', { mirek: 301 }), light('c')];

    expect(roomMirek(['a', 'b', 'c'], lights)).toBe(251);
  });

  it('has none when no lamp reports one', () => {
    expect(roomMirek(['c'], [light('c')])).toBeNull();
  });
});

describe('lightKind', () => {
  it('names what each lamp can do', () => {
    expect(lightKind(light('a', { supports_color: true, mirek_min: 153, mirek_max: 500 }))).toBe(
      'color_and_white'
    );
    expect(lightKind(light('b', { mirek_min: 153, mirek_max: 454 }))).toBe('white_ambiance');
    expect(lightKind(light('c'))).toBe('dimmable');
    expect(lightKind(light('d', { brightness: null }))).toBe('on_off');
  });
});

describe('roomBrightness', () => {
  it('reads the mean of the lights that are on, and nothing when none is', () => {
    const lights = [
      light('a', { brightness: 80 }),
      light('b', { brightness: 61 }),
      light('c', { on: false, brightness: 10 }),
      light('d', { brightness: null }),
    ];
    expect(roomBrightness(['a', 'b', 'c', 'd'], lights)).toBe(71);
    expect(roomBrightness(['c'], lights)).toBeNull();
    expect(roomBrightness([], lights)).toBeNull();
  });
});

describe('inNameOrder', () => {
  const bridge: WorkbenchLights = {
    rooms: [
      { id: 'r1', name: 'Salon', light_ids: [], on: true, ...PLAIN_ROOM },
      { id: 'r2', name: 'cuisine', light_ids: [], on: false, ...PLAIN_ROOM },
      { id: 'r3', name: 'Étage', light_ids: [], on: false, ...PLAIN_ROOM },
    ],
    lights: [
      light('a', { name: 'Lampe 10' }),
      light('b', { name: 'Lampe 2' }),
      light('c', { name: 'Applique' }),
    ],
    scenes: [
      { id: 's2', name: 'Lecture', room_id: 'r1', active: false, ...STILL },
      { id: 's1', name: 'Détente', room_id: 'r1', active: true, ...STILL },
    ],
  };

  it("puts the rooms and the lamps in alphabetical order, in the reader's language", () => {
    const sorted = inNameOrder(bridge, 'fr');
    // Case and accents do not decide, and a number is read as a number.
    expect(sorted.rooms.map(room => room.name)).toEqual(['cuisine', 'Étage', 'Salon']);
    expect(sorted.lights.map(item => item.name)).toEqual(['Applique', 'Lampe 2', 'Lampe 10']);
  });

  it('keeps the scenes as the bridge lists them, and changes nothing it was given', () => {
    const sorted = inNameOrder(bridge, 'fr');
    expect(sorted.scenes).toBe(bridge.scenes);
    expect(bridge.rooms.map(room => room.name)).toEqual(['Salon', 'cuisine', 'Étage']);
  });

  it('opens the first room in that order where none is asked', () => {
    expect(openSelection(inNameOrder(bridge, 'fr'), null, true).openId).toBe('r2');
  });
});

describe('toneTitleKey', () => {
  it('names the folded section by what the lamp can take', () => {
    expect(toneTitleKey(light('a', { supports_color: true, mirek_min: 153, mirek_max: 500 }))).toBe(
      'workbench.lights.tone'
    );
    expect(toneTitleKey(light('b', { mirek_min: 153, mirek_max: 454 }))).toBe(
      'workbench.lights.temperature'
    );
    expect(toneTitleKey(light('c', { supports_color: true }))).toBe('workbench.lights.colour');
    expect(toneTitleKey(light('d'))).toBeNull();
  });
});

describe('openSelection', () => {
  const bridge: WorkbenchLights = {
    rooms: [
      { id: 'r1', name: 'Living room', light_ids: ['a'], on: true, ...PLAIN_ROOM },
      { id: 'r2', name: 'Kitchen', light_ids: ['b'], on: false, ...PLAIN_ROOM },
    ],
    lights: [light('a'), light('b', { room_id: 'r2' }), light('c', { room_id: null })],
    scenes: [],
  };

  it('opens the room the URL names, at every width', () => {
    for (const desktop of [true, false]) {
      const open = openSelection(bridge, 'r2', desktop);
      expect([open.openId, open.openLights.map(item => item.id), open.detailOpen]).toEqual([
        'r2',
        ['b'],
        true,
      ]);
    }
  });

  it('opens the first room beside the list, and nothing where the room replaces it', () => {
    expect(openSelection(bridge, null, true).openRoom?.id).toBe('r1');
    expect(openSelection(bridge, null, false).detailOpen).toBe(false);
  });

  it('gathers the lamps no room owns under their own entry', () => {
    const open = openSelection(bridge, OTHER_LIGHTS, false);
    expect([open.openRoom, open.openLights.map(item => item.id), open.detailOpen]).toEqual([
      null,
      ['c'],
      true,
    ]);
    const roomless = { ...bridge, rooms: [] };
    expect(openSelection(roomless, null, true).openId).toBe(OTHER_LIGHTS);
  });
});

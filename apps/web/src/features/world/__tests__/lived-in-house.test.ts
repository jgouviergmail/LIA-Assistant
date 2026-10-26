import { expect, it } from 'vitest';
import { WORLD, groundAt } from '../definition';
import { compilePoseSlots } from '../pose-slots';
import { compileNavigation, findRoute, isWalkable } from '../navigation';
import { sceneActivity, seatActivity } from '../scene-activities';
import { zoneAt } from '../simulation';

const inRoom = (id: string) =>
  WORLD.props.filter(p => zoneAt(WORLD, { x: p.x + p.width / 2, y: p.y + p.depth / 2 }) === id);
it('authors every requested room as one connected furnished house with a separate private studio', () => {
  const requested = [
    'arrival',
    'meeting',
    'multimedia',
    'phone',
    'memory',
    'cafeteria',
    'engineering',
    'gym',
    'divination',
    'library',
    'restroom',
    'garden',
    'terrace',
    'home',
  ];
  expect(WORLD.zones.map(z => z.id).sort()).toEqual(requested.sort());
  const nav = compileNavigation(WORLD);
  for (const room of WORLD.zones) {
    expect(isWalkable(nav, room.arrival), room.id).toBe(true);
    expect(findRoute(nav, WORLD.spawn, room.arrival).length, room.id).toBeGreaterThan(0);
    expect(inRoom(room.id).filter(p => p.kind !== 'partition').length, room.id).toBeGreaterThan(3);
  }
});
it('provides the specified functional furniture and exact gallery family on its confirmed seat', () => {
  const count = (room: string, kind: string) => inRoom(room).filter(p => p.kind === kind).length;
  expect(count('meeting', 'chair')).toBe(7);
  expect(count('memory', 'readingdesk')).toBe(6);
  expect(count('memory', 'chair')).toBe(6);
  expect(count('library', 'readingdesk')).toBe(3);
  expect(count('multimedia', 'arcade')).toBe(3);
  expect(count('engineering', 'labtable')).toBe(3);
  expect(count('divination', 'chair')).toBe(4);
  const slots = compilePoseSlots(WORLD);
  for (const tab of ['images', 'documents', 'screenshots', 'bookmarks'] as const) {
    const easel = inRoom('multimedia').find(
      p => p.kind === 'easel' && p.activity === 'asset-' + tab
    );
    expect(easel, tab).toBeDefined();
    expect(sceneActivity(easel!.id)).toEqual({ kind: 'gallery', tab });
    const chair = inRoom('multimedia').find(
      p => p.kind === 'chair' && p.activity === easel!.activity
    );
    const slot = slots.find(s => s.prop === chair?.id);
    expect(slot, tab).toBeDefined();
    expect(seatActivity(slot!.id)).toEqual({ kind: 'gallery', tab });
  }
  const wc = slots.find(s => WORLD.props.find(p => p.id === s.prop)?.kind === 'toilet');
  expect(wc?.kind).toBe('sit');
  expect(seatActivity(wc!.id)).toEqual({ kind: 'workspace', id: 'sms' });
});
it('faces all three places of each hall bench towards the fountain with reachable approaches', () => {
  const fountain = inRoom('arrival').find(p => p.kind === 'fountain')!;
  expect(fountain).toBeDefined();
  const center = { x: fountain.x + fountain.width / 2, y: fountain.y + fountain.depth / 2 };
  const benches = inRoom('arrival').filter(p => p.kind === 'bench');
  expect(benches).toHaveLength(4);
  const slots = compilePoseSlots(WORLD);
  const dirs = [
    { x: 1, y: 0 },
    { x: 0, y: 1 },
    { x: -1, y: 0 },
    { x: 0, y: -1 },
  ];
  for (const bench of benches) {
    const seats = slots.filter(s => s.prop === bench.id);
    expect(seats).toHaveLength(3);
    for (const s of seats) {
      const d = dirs[s.facing];
      expect((center.x - s.position.x) * d.x + (center.y - s.position.y) * d.y).toBeGreaterThan(0);
    }
  }
});
it('keeps every pose approach accessible and every activity object reachable without crossing furniture', () => {
  const nav = compileNavigation(WORLD);
  for (const slot of compilePoseSlots(WORLD)) {
    expect(isWalkable(nav, slot.approach), slot.id).toBe(true);
    expect(findRoute(nav, WORLD.spawn, slot.approach).length, slot.id).toBeGreaterThan(0);
    const owner = WORLD.props.find(p => p.id === slot.prop)!;
    expect(slot.position.x, slot.id).toBeGreaterThanOrEqual(owner.x);
    expect(slot.position.x, slot.id).toBeLessThanOrEqual(owner.x + owner.width);
    expect(slot.position.y, slot.id).toBeGreaterThanOrEqual(owner.y);
    expect(slot.position.y, slot.id).toBeLessThanOrEqual(owner.y + owner.depth);
  }
});
it('uses marble in the social hall, carpet in meetings, and a true checkerboard family in the diner', () => {
  for (const [id, kind] of [
    ['arrival', 'marble'],
    ['meeting', 'carpet'],
    ['cafeteria', 'checker'],
  ] as const) {
    const room = WORLD.zones.find(z => z.id === id)!;
    expect(groundAt(WORLD, room.x + 2, room.y + 2)).toBe(kind);
  }
});

it('places the presentation screen opposite the chair at the head of the meeting table', () => {
  const props = inRoom('meeting');
  const table = props.find(p => p.kind === 'meetingtable')!;
  const boss = props.find(p => p.key === 'meeting-boss')!;
  const screen = props.find(p => p.kind === 'display')!;
  const center = { x: table.x + table.width / 2, y: table.y + table.depth / 2 };
  const head = { x: boss.x + boss.width / 2 - center.x, y: boss.y + boss.depth / 2 - center.y };
  const projection = {
    x: screen.x + screen.width / 2 - center.x,
    y: screen.y + screen.depth / 2 - center.y,
  };
  expect(head.x * projection.x + head.y * projection.y).toBeLessThan(0);
  expect(Math.abs(head.x * projection.y - head.y * projection.x)).toBeLessThan(0.5);
  expect(screen.facing).toBe(1);
});

import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { compileNavigation, findRoute } from '../navigation';
import { compilePoseSlots } from '../pose-slots';

it('keeps the everyday rooms in one connected building with short journeys', () => {
  const rooms = WORLD.zones.filter(z => z.covered && z.id !== 'home');
  for (const room of rooms) {
    const neighbours = rooms.filter(
      other =>
        other !== room &&
        ((Math.max(room.x, other.x) < Math.min(room.x + room.width, other.x + other.width) &&
          Math.max(room.y, other.y) < Math.min(room.y + room.height, other.y + other.height)) ||
          ((room.x + room.width === other.x || other.x + other.width === room.x) &&
            Math.max(room.y, other.y) < Math.min(room.y + room.height, other.y + other.height)) ||
          ((room.y + room.height === other.y || other.y + other.height === room.y) &&
            Math.max(room.x, other.x) < Math.min(room.x + room.width, other.x + other.width)))
    );
    expect(neighbours.length, room.id + ' must adjoin another room').toBeGreaterThan(0);
    const route = findRoute(compileNavigation(WORLD), WORLD.spawn, room.arrival);
    expect(route.length, room.id).toBeGreaterThan(0);
    let previous = WORLD.spawn,
      length = 0;
    for (const point of route) {
      length += Math.hypot(point.x - previous.x, point.y - previous.y);
      previous = point;
    }
    expect(length, room.id + ' should be near the shared hall').toBeLessThan(45);
  }
});

it('keeps authored solid furniture separate and leaves all sitting approaches clear', () => {
  const solid = WORLD.props.filter(p => p.blocking);
  for (let i = 0; i < solid.length; i++) {
    const a = solid[i];
    for (let j = i + 1; j < solid.length; j++) {
      const b = solid[j];
      const overlap =
        a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.depth && a.y + a.depth > b.y;
      expect(overlap, a.id + ' overlaps ' + b.id).toBe(false);
    }
  }
  const nav = compileNavigation(WORLD);
  for (const slot of compilePoseSlots(WORLD)) {
    expect(findRoute(nav, WORLD.spawn, slot.approach).length, slot.id).toBeGreaterThan(0);
    const prop = WORLD.props.find(p => p.id === slot.prop)!;
    expect(
      WORLD.zones.some(
        z => prop.x >= z.x && prop.y >= z.y && prop.x < z.x + z.width && prop.y < z.y + z.height
      ),
      slot.id + ' must have a named destination'
    ).toBe(true);
  }
});

it('places outdoor activities on uncovered furnished terraces and keeps the home separate', () => {
  for (const id of ['terrace', 'garden']) {
    const zone = WORLD.zones.find(z => z.id === id)!;
    expect(zone.covered, id).not.toBe(true);
    expect(
      WORLD.props.some(
        p =>
          ['chair', 'bench', 'lounger'].includes(p.kind) &&
          p.x >= zone.x &&
          p.x < zone.x + zone.width &&
          p.y >= zone.y &&
          p.y < zone.y + zone.height
      )
    ).toBe(true);
  }
  const home = WORLD.zones.find(z => z.id === 'home')!;
  expect(home.covered).toBe(true);
  expect(findRoute(compileNavigation(WORLD), WORLD.spawn, home.arrival).length).toBeGreaterThan(0);
});

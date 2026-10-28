import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { roomModel } from '../art/room-models';
import { compilePoseSlots } from '../pose-slots';
import { barbellModel } from '../art/barbell';
it('gives each of the three machines a distinct moving mechanism within its sprite bounds', () => {
  const machines = WORLD.props.filter(prop => prop.kind === 'machine');
  expect(machines).toHaveLength(3);
  const identities = new Set<string>();
  for (const prop of machines) {
    const rest = roomModel(prop);
    const active = roomModel(prop, { machine: 0.35 });
    expect(active).not.toEqual(rest);
    expect(roomModel(prop, { machine: 0.7 })).not.toEqual(active);
    identities.add(JSON.stringify(active));
    expect(
      active?.every(
        part =>
          part.kind !== 'box' ||
          [part.x, part.y, part.z, part.width, part.depth, part.height].every(Number.isFinite)
      )
    ).toBe(true);
  }
  expect(identities.size).toBe(3);
});
it('provides two lying workout poses and moves the bar through a full press without moving furniture', () => {
  const slots = compilePoseSlots(WORLD).filter(slot => slot.id.startsWith('workout-'));
  expect(slots).toHaveLength(2);
  for (const slot of slots) {
    expect(slot.kind).toBe('lie');
    const prop = WORLD.props.find(p => p.id === slot.prop);
    if (!prop) throw new Error('Missing bench');
    expect(roomModel(prop, { press: 1 })).toEqual(roomModel(prop, { press: 0 }));
    expect(barbellModel(2, { press: 1 })).not.toEqual(barbellModel(2, { press: 0 }));
    expect(
      roomModel(prop, { press: 0 })?.some(part => part.kind === 'face' && part.points.length === 8)
    ).toBe(false);
  }
  expect(compilePoseSlots(WORLD).some(slot => slot.id === 'health:0')).toBe(false);
});

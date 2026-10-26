import { compilePoseSlots } from '../pose-slots';
import { describe, expect, it, vi } from 'vitest';
import { WORLD } from '../definition';
import { createSimulation, stepSimulation } from '../simulation';
import { SceneInteractions, type SceneTarget } from '../scene-interactions';

const workboard = WORLD.props.find(prop => prop.key === 'workboard')!;
const desk: SceneTarget = { kind: 'object', id: workboard.id };
function setup() {
  const sim = createSimulation(WORLD);
  const host = { canOpen: vi.fn((_target: SceneTarget) => true), open: vi.fn(() => true) };
  const scene = new SceneInteractions(sim, host);
  return { sim, host, scene };
}
function arrive(value: ReturnType<typeof setup>) {
  for (let i = 0; i < 3000 && !value.host.open.mock.calls.length; i++) {
    stepSimulation(value.sim, 1 / 60, { x: 0, y: 0 });
    value.scene.update();
  }
}
describe('contextual world interactions', () => {
  it('approaches a real object through walkable space before opening its private activity once', () => {
    const value = setup();
    expect(value.scene.choose(desk)).toBe(true);
    expect(value.host.open).not.toHaveBeenCalled();
    expect(value.sim.player.path.length).toBeGreaterThan(0);
    arrive(value);
    expect(value.host.open).toHaveBeenCalledExactlyOnceWith(desk);
    value.scene.update();
    expect(value.host.open).toHaveBeenCalledTimes(1);
  });
  it('rechecks authority on arrival and cancels a suspended or manually interrupted approach', () => {
    const value = setup();
    value.scene.choose(desk);
    value.host.canOpen.mockReturnValue(false);
    arrive(value);
    expect(value.host.open).not.toHaveBeenCalled();
    value.host.canOpen.mockReturnValue(true);
    value.scene.choose(desk);
    value.scene.cancel();
    arrive(value);
    expect(value.host.open).not.toHaveBeenCalled();
  });
  it('refuses unknown and inaccessible objects rather than opening from across a wall', () => {
    const value = setup();
    expect(value.scene.choose({ kind: 'object', id: 'invented' })).toBe(false);
    value.sim.navigation.blocked.fill(1);
    expect(value.scene.choose(desk)).toBe(false);
    expect(value.host.open).not.toHaveBeenCalled();
  });
  it('opens only a currently present person, without walking into them', () => {
    const value = setup();
    expect(value.scene.choose({ kind: 'peer', id: 'departed' })).toBe(false);
    expect(value.scene.choose({ kind: 'lia' })).toBe(true);
    expect(value.host.open).toHaveBeenCalledExactlyOnceWith({ kind: 'lia' });
    expect(value.sim.player.path).toEqual([]);
  });
  it('does not offer a nearby object through a wall', () => {
    const value = setup();
    value.sim.player.position = { x: workboard.x + 0.5, y: workboard.y - 0.5 };
    value.host.canOpen.mockImplementation(
      target => target.kind === 'object' && target.id === desk.id
    );
    expect(value.scene.nearest()).toEqual(desk);
    value.sim.navigation.blocked.fill(1);
    expect(value.scene.nearest()).toBeNull();
  });
});

it('offers and opens a present peer, but exposes no activity in the unconnected prototype', () => {
  const value = setup();
  const position = { x: value.sim.player.position.x + 0.5, y: value.sim.player.position.y + 0.5 };
  value.sim.visitors = [
    {
      ...value.sim.player,
      id: 'peer',
      label: 'Peer',
      position,
      from: position,
      target: position,
      blend: 1,
    },
  ];
  value.host.canOpen.mockImplementation(target => target.kind === 'peer');
  expect(value.scene.nearest()).toEqual({ kind: 'peer', id: 'peer' });
  expect(value.scene.choose({ kind: 'peer', id: 'peer' })).toBe(true);
  expect(value.host.open).toHaveBeenCalledExactlyOnceWith({ kind: 'peer', id: 'peer' });
  const local = new SceneInteractions(value.sim);
  expect(local.nearest()).toBeNull();
  expect(local.choose(desk)).toBe(false);
});
it('expires an unfinished approach instead of opening an old intent on a later arrival', () => {
  const value = setup();
  value.scene.choose(desk);
  value.sim.time += 61;
  value.scene.update();
  expect(value.sim.player.path).toEqual([]);
  arrive(value);
  expect(value.host.open).not.toHaveBeenCalled();
});

it('resolves furniture to a free stable place and approaches its authored entry before posing', () => {
  const value = setup();
  const slots = compilePoseSlots(WORLD).filter(slot => slot.id.startsWith('media-sofa-n:'));
  const object: SceneTarget = { kind: 'object', id: slots[0].prop };
  const target = value.scene.resolve(object);
  expect(target.kind).toBe('pose');
  value.sim.visitors = [
    {
      ...value.sim.player,
      id: 'seated',
      label: 'Peer',
      pose: slots[0],
      from: slots[0].position,
      target: slots[0].position,
      blend: 1,
    },
  ];
  expect(value.scene.resolve(object)).toEqual({ kind: 'pose', id: slots[1].id, action: 'sit' });
  expect(value.scene.choose(value.scene.resolve(object))).toBe(true);
  arrive(value);
  expect(value.host.open).toHaveBeenCalledExactlyOnceWith({
    kind: 'pose',
    id: slots[1].id,
    action: 'sit',
  });
  value.sim.visitors.push({ ...value.sim.visitors[0], id: 'second', pose: slots[1] });
  expect(value.scene.resolve(object).kind).toBe('pose');
  expect(value.scene.resolve(desk)).toEqual(desk);
  expect(value.scene.resolve({ kind: 'lia' })).toEqual({ kind: 'lia' });
  expect(value.scene.choose({ kind: 'pose', id: 'missing', action: 'sit' })).toBe(false);
});
it('offers standing while seated and waits for server proximity before sending a pose once', () => {
  const value = setup();
  const slot = compilePoseSlots(WORLD)[0];
  value.sim.player.pose = slot;
  expect(value.scene.nearest()).toEqual({ kind: 'stand' });
  expect(value.scene.choose({ kind: 'stand' })).toBe(true);
  value.sim.player.pose = null;
  value.host.open.mockClear().mockReturnValue(false);
  value.scene.choose({ kind: 'pose', id: slot.id, action: slot.kind });
  arrive(value);
  expect(value.host.open).toHaveBeenCalled();
  value.host.open.mockClear().mockReturnValue(true);
  value.scene.update();
  value.scene.update();
  expect(value.host.open).toHaveBeenCalledTimes(1);
});

it('stands before approaching another object and cancels that intent on interruption', () => {
  const value = setup();
  const slot = compilePoseSlots(WORLD)[0];
  value.sim.player.pose = slot;
  value.sim.player.position = slot.position;
  expect(value.scene.choose(desk)).toBe(true);
  expect(value.host.open).toHaveBeenCalledExactlyOnceWith({ kind: 'stand' });
  value.scene.update();
  expect(value.sim.player.path).toEqual([]);
  value.sim.player.pose = null;
  value.sim.player.position = slot.approach;
  value.scene.update();
  expect(value.sim.player.path.length).toBeGreaterThan(0);
  value.scene.cancel();
  value.host.open.mockClear();
  arrive(value);
  expect(value.host.open).not.toHaveBeenCalled();
});

it('does not retain a seated intent when standing is refused or its acknowledgment times out', () => {
  const value = setup();
  const slot = compilePoseSlots(WORLD)[0];
  value.sim.player.pose = slot;
  value.sim.player.position = slot.position;
  value.host.open.mockReturnValue(false);
  expect(value.scene.choose(desk)).toBe(false);
  value.host.open.mockReturnValue(true);
  expect(value.scene.choose(desk)).toBe(true);
  value.sim.time += 6;
  value.scene.update();
  value.sim.player.pose = null;
  value.sim.player.position = slot.approach;
  value.scene.update();
  expect(value.sim.player.path).toEqual([]);
});

it('approaches a distant peer before opening and cancels when the peer leaves', () => {
  const value = setup();
  const position = WORLD.zones.find(zone => zone.id === 'cafeteria')!.arrival;
  value.sim.visitors = [
    {
      ...value.sim.player,
      id: 'distant',
      label: 'Peer',
      position,
      from: position,
      target: position,
      blend: 1,
    },
  ];
  const peer: SceneTarget = { kind: 'peer', id: 'distant' };
  expect(value.scene.choose(peer)).toBe(true);
  expect(value.host.open).not.toHaveBeenCalled();
  arrive(value);
  expect(
    Math.hypot(value.sim.player.position.x - position.x, value.sim.player.position.y - position.y)
  ).toBeLessThanOrEqual(2.5);
  expect(value.host.open).toHaveBeenCalledExactlyOnceWith(peer);
  value.host.open.mockClear();
  value.sim.player.position = { ...WORLD.spawn };
  value.scene.choose(peer);
  value.sim.visitors = [];
  arrive(value);
  expect(value.host.open).not.toHaveBeenCalled();
  expect(value.sim.player.path).toEqual([]);
});
it('never starts a conversation through an impassable wall', () => {
  const value = setup();
  value.sim.navigation.blocked.fill(1);
  expect(value.scene.choose({ kind: 'lia' })).toBe(false);
  expect(value.host.open).not.toHaveBeenCalled();
});

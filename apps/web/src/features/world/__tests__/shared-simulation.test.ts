import { compilePoseSlots } from '../pose-slots';
import { describe, expect, it, vi } from 'vitest';
import { WORLD } from '../definition';
import { createSimulation, walkTo } from '../simulation';
import { MOVEMENT } from '../movement';
import { ACTOR_RADIUS, isWalkable } from '../navigation';
import { WorldSynchronizer } from '../shared-simulation';
import type { WorldView } from '../protocol';
import type { Point } from '../types';

const epoch = '4010c2c2-4bd0-4d21-9c08-b4502db25d72';
function snapshot(): WorldView {
  return {
    server_time: 100,
    receipts: [],
    type: 'snapshot',
    version: 2,
    epoch,
    revision: 1,
    status: 'active',
    actors: [],
    you: { id: epoch, alias: 'You', position: { ...WORLD.spawn }, facing: 1, walking: false },
    ack: 0,
    controlling: true,
    position: null,
    offer_until: null,
    idle_until: 1000,
  };
}
function setup() {
  let seq = 0;
  const link = {
    view: snapshot(),
    stream: 1,
    canMove: true,
    motion: vi.fn((_direction: Point) => ++seq),
  };
  return { link, sync: new WorldSynchronizer(link), sim: createSimulation(WORLD) };
}
describe('bounded prediction and public visitors', () => {
  it('keeps a clear route stable across an ordinary server snapshot', () => {
    const { link, sync, sim } = setup();
    sync.step(sim, 1 / 60, { x: 0, y: 0 });
    const goal = { x: WORLD.spawn.x + 1, y: WORLD.spawn.y };
    expect(walkTo(sim, goal)).toBe(true);
    const route = sim.player.path;
    link.view = { ...link.view, revision: 2 };
    sync.step(sim, 1 / 60, { x: 0, y: 0 });
    expect(sim.player.path).toBe(route);
    expect(sim.player.path.at(-1)).toEqual(goal);
    expect(link.motion).not.toHaveBeenCalled();
  });
  it('rebases a remaining route when authoritative correction would cut a chair corner', () => {
    const { link, sync, sim } = setup();
    sync.step(sim, 1 / 60, { x: 0, y: 0 });
    const goal = { x: 44.5, y: 40.5 };
    sim.player.path = [goal];
    link.view = {
      ...link.view,
      you: { ...link.view.you!, position: { x: 44.19468665023537, y: 42.234835147140835 } },
    };
    sync.step(sim, 1 / 60, { x: 0, y: 0 });
    for (const dx of [-ACTOR_RADIUS, ACTOR_RADIUS])
      for (const dy of [-ACTOR_RADIUS, ACTOR_RADIUS])
        expect(
          isWalkable(sim.navigation, {
            x: sim.player.position.x + dx,
            y: sim.player.position.y + dy,
          })
        ).toBe(true);
    expect(sim.player.path.at(-1)).toEqual(goal);
    expect(sim.player.position.y).toBeGreaterThan(link.view.you!.position.y);
  });
  it('does not carry a walking destination into a new authoritative epoch', () => {
    const { link, sync, sim } = setup();
    sync.step(sim, 1 / 60, { x: 0, y: 0 });
    expect(walkTo(sim, { x: WORLD.spawn.x + 1, y: WORLD.spawn.y })).toBe(true);
    link.view = { ...link.view, epoch: '6010c2c2-4bd0-4d21-9c08-b4502db25d72' };
    sync.step(sim, 1 / 60, { x: 0, y: 0 });
    expect(sim.player.path).toEqual([]);
    expect(sim.player.position).toEqual(WORLD.spawn);
    expect(link.motion).not.toHaveBeenCalled();
  });
  it('predicts locally, sends intent at ten hertz and reconciles only unacknowledged movement', () => {
    const { link, sync, sim } = setup();
    for (let n = 0; n < 6; n++) sync.step(sim, 1 / 60, { x: 1, y: 0 });
    expect(link.motion).toHaveBeenCalledTimes(1);
    expect(link.motion.mock.calls[0][0].x).toBeCloseTo(1);
    expect(link.motion.mock.calls[0][0].y).toBe(0);
    expect(sim.player.position.x).toBeCloseTo(WORLD.spawn.x + 0.34);
    const you = link.view.you!;
    link.view = {
      ...link.view,
      revision: 2,
      ack: 1,
      you: { ...you, position: { x: WORLD.spawn.x + 0.2, y: WORLD.spawn.y } },
    };
    sync.step(sim, 1 / 60, { x: 0, y: 0 });
    expect(sim.player.position.x).toBeCloseTo(WORLD.spawn.x + 0.2);
  });
  it('freezes movement and cancels click paths when authority is stale or control is lost', () => {
    const { link, sync, sim } = setup();
    sim.player.path = [{ x: 40, y: 32 }];
    link.canMove = false;
    sync.step(sim, 0.1, { x: 1, y: 0 });
    expect(sim.player.path).toEqual([]);
    expect(sim.player.position).toEqual(WORLD.spawn);
    expect(link.motion).not.toHaveBeenCalled();
  });
  it('removes a departed/private/blocked visitor immediately and resets predictions across epochs', () => {
    const { link, sync, sim } = setup();
    link.view = {
      ...link.view,
      actors: [{ ...link.view.you!, id: '5010c2c2-4bd0-4d21-9c08-b4502db25d72', alias: 'Visitor' }],
    };
    sync.step(sim, 0.1, { x: 1, y: 0 });
    expect(sim.visitors).toHaveLength(1);
    link.stream++;
    link.view = { ...snapshot(), epoch: '6010c2c2-4bd0-4d21-9c08-b4502db25d72' };
    sync.step(sim, 1 / 60, { x: 0, y: 0 });
    expect(sim.visitors).toEqual([]);
    expect(sim.player.position).toEqual(WORLD.spawn);
  });
});

it('orients a remote person from their actual diagonal displacement and retains it when stopping', () => {
  const { link, sync, sim } = setup();
  const person = {
    ...link.view.you!,
    id: '5010c2c2-4bd0-4d21-9c08-b4502db25d72',
    alias: 'Visitor',
    position: { x: 34, y: 32 },
  };
  link.view = { ...link.view, actors: [person] };
  sync.step(sim, 0.1, { x: 0, y: 0 });
  link.view = {
    ...link.view,
    revision: 2,
    actors: [{ ...person, position: { x: 34.2, y: 32.2 }, walking: true, facing: 1 }],
  };
  sync.step(sim, 0.1, { x: 0, y: 0 });
  expect(sim.visitors[0].heading).toBe(1);
  const phase = sim.visitors[0].phase;
  link.view = { ...link.view, revision: 3, actors: [{ ...link.view.actors[0], walking: false }] };
  sync.step(sim, 0.1, { x: 0, y: 0 });
  expect(sim.visitors[0].heading).toBe(1);
  expect(sim.visitors[0].phase).toBe(phase);
});

it('waits for authoritative standing before predicting out of occupied furniture', () => {
  const { link, sync, sim } = setup();
  const slot = compilePoseSlots(WORLD).find(s => s.kind === 'sit')!;
  link.view = {
    ...link.view,
    you: { ...link.view.you!, pose: slot.id, position: slot.position, facing: slot.facing },
  };
  for (let i = 0; i < 12; i++) sync.step(sim, 1 / 60, { x: 1, y: 0 });
  expect(sim.player.position).toEqual(slot.position);
  expect(sim.player.walking).toBe(false);
  expect(sim.player.heading).toBe(slot.facing * 2);
  expect(link.motion).toHaveBeenCalled();
  link.view = {
    ...link.view,
    ack: 3,
    revision: 2,
    you: { ...link.view.you!, pose: null, position: slot.approach },
  };
  sync.step(sim, 0.1, { x: 1, y: 0 });
  expect(sim.player.pose).toBeNull();
  expect(sim.player.position.x).toBeGreaterThan(slot.approach.x);
});
it('does not interpolate seated peers through their furniture or walk their legs in place', () => {
  const { link, sync, sim } = setup();
  const slot = compilePoseSlots(WORLD).find(s => s.kind === 'sit')!;
  const person = { ...link.view.you!, id: '5010c2c2-4bd0-4d21-9c08-b4502dbd1111' };
  link.view = { ...link.view, actors: [person] };
  sync.step(sim, 0.1, { x: 0, y: 0 });
  link.view = {
    ...link.view,
    revision: 2,
    actors: [{ ...person, pose: slot.id, position: slot.position, facing: slot.facing }],
  };
  sync.step(sim, 1 / 60, { x: 0, y: 0 });
  expect(sim.visitors[0].position).toEqual(slot.position);
  expect(sim.visitors[0].walking).toBe(false);
  expect(sim.visitors[0].heading).toBe(slot.facing * 2);
});

it('does not allow a pose to overtake the last unsent or unacknowledged movement', () => {
  const { link, sync, sim } = setup();
  sync.step(sim, 1 / 60, { x: 1, y: 0 });
  expect(sync.settled).toBe(false);
  for (let i = 0; i < 5; i++) sync.step(sim, 1 / 60, { x: 0, y: 0 });
  expect(link.motion).toHaveBeenCalledTimes(1);
  expect(sync.settled).toBe(false);
  link.view = {
    ...link.view,
    revision: 2,
    ack: 1,
    you: { ...link.view.you!, position: { ...sim.player.position } },
  };
  sync.step(sim, 1 / 60, { x: 0, y: 0 });
  expect(sync.settled).toBe(true);
  for (let i = 0; i < 30; i++) sync.step(sim, 1 / 60, { x: 0, y: 0 });
  expect(link.motion).toHaveBeenCalledTimes(1);
});

it('encodes a mixed walking/running packet without exceeding or slowing its authoritative displacement', () => {
  const { sim, sync, link } = setup();
  const goal = { x: WORLD.spawn.x, y: WORLD.spawn.y + 5 };
  walkTo(sim, goal);
  for (let i = 0; i < 3; i++) sync.step(sim, 1 / 60, { x: 0, y: 0 });
  walkTo(sim, goal, true);
  for (let i = 0; i < 3; i++) sync.step(sim, 1 / 60, { x: 0, y: 0 });
  expect(link.motion).toHaveBeenCalledTimes(1);
  expect(link.motion).toHaveBeenCalledWith(
    { x: 0, y: expect.closeTo((MOVEMENT.walk + MOVEMENT.run) / (2 * MOVEMENT.run), 6) },
    true
  );
  expect(sim.player.position.y - WORLD.spawn.y).toBeCloseTo((MOVEMENT.walk + MOVEMENT.run) * 0.05);
});

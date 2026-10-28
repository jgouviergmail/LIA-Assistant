import { expect, it, vi } from 'vitest';
import { CosmeticController } from '../cosmetic-controller';
import { cosmeticPropTarget } from '../cosmetic-interactions';
import { SceneInteractions, objectApproaches } from '../scene-interactions';
import { WORLD } from '../definition';
import { createSimulation, stepSimulation } from '../simulation';
import { compilePoseSlots } from '../pose-slots';

it('does not react to an unconfirmed or rejected workout pose and releases a pose when its effect cannot start', () => {
  const sim = createSimulation(WORLD);
  const prop = WORLD.props.find(item => item.key === 'workout-1');
  const slot = compilePoseSlots(WORLD).find(item => item.id === 'workout-1:0');
  if (!prop || !slot) throw new Error('Missing workout');
  sim.player.position = { ...slot.approach };
  const open = vi.fn(() => true),
    activate = vi.fn(() => false),
    cue = vi.fn();
  const host = new CosmeticController(sim, {
    networked: true,
    parent: { canOpen: () => true, open },
    target: id => (id === prop.id ? cosmeticPropTarget(prop) : null),
    activate,
    cancel: vi.fn(),
    cue,
  });
  host.open({ kind: 'object', id: prop.id });
  sim.time = 6;
  host.update();
  sim.player.pose = slot;
  host.update();
  expect(activate).not.toHaveBeenCalled();
  expect(cue).not.toHaveBeenCalled();
  sim.player.pose = null;
  sim.player.position = { ...slot.approach };
  open.mockReturnValueOnce(false);
  expect(host.open({ kind: 'object', id: prop.id })).toBe(false);
  expect(activate).not.toHaveBeenCalled();
  host.open({ kind: 'object', id: prop.id });
  sim.player.pose = slot;
  host.update();
  expect(activate).toHaveBeenCalledOnce();
  expect(open).toHaveBeenLastCalledWith({ kind: 'stand' });
  expect(cue).not.toHaveBeenCalled();
});

it('waits for the actual shared lying pose, cues exactly three lifts and stands through the native host', () => {
  const sim = createSimulation(WORLD);
  const prop = WORLD.props.find(item => item.key === 'workout-1');
  const slot = compilePoseSlots(WORLD).find(item => item.id === 'workout-1:0');
  if (!prop || !slot) throw new Error('Missing authored workout pose');
  sim.player.position = { ...slot.approach };
  const activate = vi.fn(() => true),
    open = vi.fn(() => true),
    cue = vi.fn(),
    cancel = vi.fn();
  const host = new CosmeticController(sim, {
    networked: true,
    parent: { canOpen: () => true, open },
    target: id => (id === prop.id ? cosmeticPropTarget(prop) : null),
    activate,
    cancel,
    cue,
  });
  expect(host.open({ kind: 'object', id: prop.id })).toBe(true);
  expect(open).toHaveBeenCalledExactlyOnceWith({ kind: 'pose', id: slot.id, action: 'lie' });
  host.update();
  expect(activate).not.toHaveBeenCalled();
  expect(sim.player.pose).toBeUndefined();
  sim.player.pose = slot;
  sim.player.position = { ...slot.position };
  host.update();
  expect(activate).toHaveBeenCalledExactlyOnceWith(prop.id);
  expect(cue).not.toHaveBeenCalled();
  for (const time of [0.85, 2.2, 3.5]) {
    sim.time = time;
    host.update();
  }
  expect(cue).toHaveBeenCalledTimes(3);
  sim.time = 5.3;
  host.update();
  expect(open).toHaveBeenLastCalledWith({ kind: 'stand' });
  host.update();
  expect(cue).toHaveBeenCalledTimes(3);
});

it('uses the real walkable route and plays once only after arrival; cancellation fences late audio', () => {
  const sim = createSimulation(WORLD);
  const plant = WORLD.props.find(prop => prop.kind === 'plant');
  if (!plant) throw new Error('Missing plant');
  const target = cosmeticPropTarget(plant);
  const activate = vi.fn(() => true),
    cue = vi.fn(),
    cancel = vi.fn();
  const host = new CosmeticController(sim, {
    networked: false,
    target: id => (id === plant.id ? target : null),
    activate,
    cancel,
    cue,
  });
  const scene = new SceneInteractions(sim, host);
  expect(host.open({ kind: 'object', id: plant.id })).toBe(false);
  expect(scene.choose({ kind: 'object', id: plant.id })).toBe(true);
  expect(activate).not.toHaveBeenCalled();
  for (let i = 0; i < 3500 && !activate.mock.calls.length; i++) {
    stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
    scene.update();
    host.update();
  }
  expect(activate).toHaveBeenCalledExactlyOnceWith(plant.id);
  expect(cue).toHaveBeenCalledOnce();
  const valid = cue.mock.calls[0][1];
  expect(valid()).toBe(true);
  host.cancel();
  scene.cancel();
  expect(valid()).toBe(false);
  for (let i = 0; i < 60; i++) host.update();
  expect(activate).toHaveBeenCalledTimes(1);
  expect(host.open({ kind: 'pose', id: 'unknown', action: 'lie' })).toBe(false);
});
it('does not play an unreachable or withdrawn object, and never falls back to a local pose for a shared actor', () => {
  const sim = createSimulation(WORLD);
  const plant = WORLD.props.find(prop => prop.kind === 'plant');
  if (!plant) throw new Error('Missing plant');
  const activate = vi.fn(() => true);
  const host = new CosmeticController(sim, {
    networked: true,
    target: id => (id === plant.id ? cosmeticPropTarget(plant) : null),
    activate,
    cancel: vi.fn(),
    cue: vi.fn(),
  });
  const scene = new SceneInteractions(sim, host);
  sim.navigation.blocked.fill(1);
  expect(scene.choose({ kind: 'object', id: plant.id })).toBe(false);
  expect(host.canOpen({ kind: 'pose', id: 'atrium-n:0', action: 'sit' })).toBe(false);
  expect(activate).not.toHaveBeenCalled();
});

it.each(['pond', 'fountain', 'billiards', 'machine'] as const)(
  'reaches the authored %s from campus admission before activating it',
  kind => {
    const sim = createSimulation(WORLD);
    const prop = WORLD.props.find(item => item.kind === kind);
    if (!prop) throw new Error('Missing authored decor');
    const activate = vi.fn(() => true);
    const host = new CosmeticController(sim, {
      networked: false,
      target: id => (id === prop.id ? cosmeticPropTarget(prop) : null),
      activate,
      cancel: vi.fn(),
      cue: vi.fn(),
    });
    const scene = new SceneInteractions(sim, host);
    expect(scene.choose({ kind: 'object', id: prop.id })).toBe(true);
    expect(activate).not.toHaveBeenCalled();
    for (let i = 0; i < 3600 && !activate.mock.calls.length; i++) {
      stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
      scene.update();
      host.update();
    }
    expect(activate).toHaveBeenCalledExactlyOnceWith(prop.id);
  }
);
it('permits offline posing while refusing to fabricate the same pose for an unbound networked owner', () => {
  const sim = createSimulation(WORLD);
  const slot = compilePoseSlots(WORLD).find(item => item.id === 'workout-1:0');
  if (!slot) throw new Error('Missing workout');
  const options = {
    networked: false,
    target: () => null,
    activate: vi.fn(() => true),
    cancel: vi.fn(),
    cue: vi.fn(),
  };
  const local = new CosmeticController(sim, options);
  const pose = { kind: 'pose', id: slot.id, action: slot.kind } as const;
  expect(local.canOpen(pose)).toBe(true);
  expect(local.canOpen({ kind: 'peer', id: 'unknown' })).toBe(false);
  expect(local.canOpen({ kind: 'object', id: 'unknown' })).toBe(false);
  expect(local.open({ kind: 'peer', id: 'unknown' })).toBe(false);
  expect(local.open({ kind: 'object', id: 'unknown' })).toBe(false);
  expect(local.open(pose)).toBe(true);
  expect(sim.player.pose).toEqual(slot);
  expect(sim.player.position).toEqual(slot.position);
  expect(local.open({ kind: 'stand' })).toBe(true);
  expect(sim.player.pose).toBeNull();
  expect(sim.player.position).toEqual(slot.approach);
  const shared = new CosmeticController(sim, { ...options, networked: true });
  expect(shared.canOpen(pose)).toBe(false);
  expect(shared.open(pose)).toBe(false);
  expect(sim.player.pose).toBeNull();
});
it('approaches moving fauna without an authored prop and refuses an absent workout slot', () => {
  const sim = createSimulation(WORLD);
  const target = {
    id: 'ambient-butterfly-0',
    action: 'butterfly',
    point: { ...WORLD.spawn },
    elevation: 1,
  } as const;
  const activate = vi.fn(() => true);
  const host = new CosmeticController(sim, {
    networked: false,
    target: () => target,
    activate,
    cancel: vi.fn(),
    cue: vi.fn(),
  });
  const scene = new SceneInteractions(sim, host);
  expect(scene.choose({ kind: 'object', id: target.id })).toBe(true);
  for (let i = 0; i < 600 && !activate.mock.calls.length; i++) {
    stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
    scene.update();
    host.update();
  }
  expect(activate).toHaveBeenCalledExactlyOnceWith(target.id);
  const broken = new CosmeticController(createSimulation({ ...WORLD, props: [] }), {
    networked: false,
    target: () => ({ ...target, action: 'workout' }),
    activate,
    cancel: vi.fn(),
    cue: vi.fn(),
  });
  expect(broken.canOpen({ kind: 'object', id: target.id })).toBe(false);
  expect(broken.approaches({ kind: 'object', id: target.id }, WORLD.spawn)).toEqual([]);
  expect(broken.open({ kind: 'object', id: target.id })).toBe(false);
});
it('withdraws a fishing reaction before its impact and invalidates the pending sound owner', () => {
  const sim = createSimulation(WORLD);
  const prop = WORLD.props.find(item => item.kind === 'pond');
  if (!prop) throw new Error('Missing pond');
  sim.player.position = objectApproaches(prop, sim.player.position)[0];
  const cancel = vi.fn(),
    cue = vi.fn();
  const host = new CosmeticController(sim, {
    networked: false,
    target: () => cosmeticPropTarget(prop),
    activate: () => true,
    cancel,
    cue,
  });
  expect(host.open({ kind: 'object', id: prop.id })).toBe(true);
  sim.time = 2.7;
  host.update();
  expect(cue).toHaveBeenCalledOnce();
  const current = cue.mock.calls[0][1];
  expect(current()).toBe(true);
  host.cancel();
  expect(cancel).toHaveBeenCalledExactlyOnceWith(prop.id);
  expect(current()).toBe(false);
  sim.time = 20;
  host.update();
  expect(cue).toHaveBeenCalledOnce();
});
it.each(['authority-loss', 'stand-timeout'] as const)(
  'bounds a workout after %s without a local authority fallback',
  cause => {
    const sim = createSimulation(WORLD);
    const slot = compilePoseSlots(WORLD).find(item => item.id === 'workout-1:0');
    const prop = WORLD.props.find(item => item.key === 'workout-1');
    if (!slot || !prop) throw new Error('Missing workout');
    sim.player.position = { ...slot.approach };
    const open = vi.fn(() => true),
      cancel = vi.fn();
    const host = new CosmeticController(sim, {
      networked: true,
      parent: { canOpen: () => true, open },
      target: () => cosmeticPropTarget(prop),
      activate: () => true,
      cancel,
      cue: vi.fn(),
    });
    expect(host.open({ kind: 'object', id: prop.id })).toBe(true);
    sim.player.pose = slot;
    host.update();
    open.mockClear().mockReturnValue(false);
    if (cause === 'authority-loss') {
      sim.player.pose = null;
      host.update();
      expect(cancel).toHaveBeenCalledExactlyOnceWith(prop.id);
      expect(open).not.toHaveBeenCalled();
    } else {
      for (const time of [5.3, 6, 8.1]) {
        sim.time = time;
        host.update();
      }
      expect(open).toHaveBeenCalledTimes(3);
      sim.time = 9;
      host.update();
      expect(open).toHaveBeenCalledTimes(3);
      expect(sim.player.pose).toBe(slot);
    }
  }
);

it('relays its parent’s momentary silence, so a pending approach freezes instead of being withdrawn', () => {
  const sim = createSimulation(WORLD);
  const desk = WORLD.props.find(prop => prop.key === 'workboard');
  if (!desk) throw new Error('Missing workboard');
  const state = { ready: true };
  const open = vi.fn(() => true);
  const options = {
    networked: true,
    target: () => null,
    activate: vi.fn(() => true),
    cancel: vi.fn(),
    cue: vi.fn(),
  };
  const host = new CosmeticController(sim, {
    ...options,
    parent: { ready: () => state.ready, canOpen: () => state.ready, open },
  });
  expect(new CosmeticController(sim, options).ready()).toBe(true);
  expect(
    new CosmeticController(sim, { ...options, parent: { canOpen: () => true, open } }).ready()
  ).toBe(true);
  const scene = new SceneInteractions(sim, host);
  expect(scene.choose({ kind: 'object', id: desk.id })).toBe(true);
  state.ready = false;
  expect(host.ready()).toBe(false);
  scene.update();
  state.ready = true;
  for (let i = 0; i < 3000 && !open.mock.calls.length; i++) {
    stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
    scene.update();
  }
  expect(open).toHaveBeenCalledExactlyOnceWith({ kind: 'object', id: desk.id });
});

import { describe, expect, it, vi } from 'vitest';
import { WORLD } from '../definition';
import { createSimulation, stepSimulation } from '../simulation';
import { SOCIAL_APPROACH_SECONDS, SocialApproach } from '../social-approach';
import { compilePoseSlots } from '../pose-slots';
import { compileNavigation } from '../navigation';
function setup() {
  const sim = createSimulation(WORLD);
  sim.bip.position = { x: 46.5, y: 30.5 };
  const host = { canOpen: vi.fn(() => true), open: vi.fn(() => true) };
  return { sim, host, approach: new SocialApproach(sim, host) };
}
describe('bounded social approach', () => {
  it('lets LIA wait and face the approaching owner, then resume her own movement', () => {
    const { sim, approach } = setup();
    sim.wait = 0;
    const before = { ...sim.bip.position };
    expect(approach.start({ kind: 'lia' })).toBe(true);
    for (let n = 0; n < 120; n++) stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
    expect(sim.bip.position).toEqual(before);
    expect(sim.bip.walking).toBe(false);
    expect(sim.bip.facing).toBe(2);
    expect(sim.bip.heading).toBe(4);
    approach.cancel();
    for (let n = 0; n < 120; n++) stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
    expect(sim.bip.position).not.toEqual(before);
  });
  it('keeps LIA roaming when the selected person is another player', () => {
    const { sim, approach } = setup();
    sim.wait = 0;
    const at = { ...sim.bip.position };
    sim.visitors = [
      { ...sim.bip, id: 'peer', label: 'Peer', position: at, from: at, target: at, blend: 1 },
    ];
    expect(approach.start({ kind: 'peer', id: 'peer' })).toBe(true);
    for (let n = 0; n < 120; n++) stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
    expect(sim.bip.position).not.toEqual(at);
  });
  it.each(['timeout', 'authority', 'obstacle'] as const)(
    'abandons the route after %s without opening a conversation',
    reason => {
      const { sim, host, approach } = setup();
      expect(approach.start({ kind: 'lia' })).toBe(true);
      if (reason === 'timeout') sim.time = SOCIAL_APPROACH_SECONDS + 1;
      if (reason === 'authority') host.canOpen.mockReturnValue(false);
      if (reason === 'obstacle') {
        sim.time = 0.6;
        sim.navigation.blocked.fill(1);
      }
      approach.update();
      expect(sim.player.path).toEqual([]);
      expect(host.open).not.toHaveBeenCalled();
      const waitingAt = { ...sim.bip.position };
      sim.navigation = compileNavigation(WORLD);
      sim.wait = 0;
      for (let n = 0; n < 120; n++) stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
      expect(sim.bip.position).not.toEqual(waitingAt);
      sim.bip.position = { ...sim.player.position };
      approach.update();
      expect(host.open).not.toHaveBeenCalled();
    }
  );
  it('retargets a moving person at a bounded cadence without opening until nearby', () => {
    const { sim, host, approach } = setup();
    expect(approach.start({ kind: 'lia' })).toBe(true);
    const previous = structuredClone(sim.player.path);
    sim.bip.position = { x: 46.5, y: 35.5 };
    sim.time = 0.4;
    approach.update();
    expect(sim.player.path).toEqual(previous);
    sim.time = 0.6;
    approach.update();
    expect(sim.player.path).not.toEqual(previous);
    expect(host.open).not.toHaveBeenCalled();
    approach.cancel();
    sim.bip.position = { ...sim.player.position };
    approach.update();
    expect(host.open).not.toHaveBeenCalled();
  });
  it('holds a person approach through a silent authority and withdraws it only at its deadline', () => {
    const sim = createSimulation(WORLD);
    sim.bip.position = { x: 46.5, y: 30.5 };
    const state = { ready: true };
    const host = {
      ready: () => state.ready,
      canOpen: vi.fn(() => state.ready),
      open: vi.fn(() => true),
    };
    const approach = new SocialApproach(sim, host);
    expect(approach.start({ kind: 'lia' })).toBe(true);
    state.ready = false;
    approach.update();
    expect(sim.player.path).toEqual([]);
    expect(sim.bipInteractionHeld).toBe(true);
    // The first update with authority back replans at once, not at the next cadence.
    state.ready = true;
    approach.update();
    expect(sim.player.path.length).toBeGreaterThan(0);
    state.ready = false;
    sim.time = SOCIAL_APPROACH_SECONDS + 1;
    approach.update();
    expect(sim.player.path).toEqual([]);
    expect(sim.bipInteractionHeld).toBe(false);
    state.ready = true;
    sim.bip.position = { ...sim.player.position };
    approach.update();
    expect(host.open).not.toHaveBeenCalled();
  });
  it('never invents authority and does not walk a seated person away from their seat', () => {
    const { sim, host, approach } = setup();
    expect(new SocialApproach(sim).start({ kind: 'lia' })).toBe(false);
    host.canOpen.mockReturnValue(false);
    expect(approach.start({ kind: 'lia' })).toBe(false);
    host.canOpen.mockReturnValue(true);
    sim.player.pose = compilePoseSlots(WORLD)[0];
    expect(approach.start({ kind: 'lia' })).toBe(false);
    expect(sim.player.path).toEqual([]);
    expect(host.open).not.toHaveBeenCalled();
  });
});

import { describe, expect, it, vi } from 'vitest';
import { WORLD } from '../definition';
import { createSimulation } from '../simulation';
import { SocialApproach } from '../social-approach';
import { compilePoseSlots } from '../pose-slots';
function setup() {
  const sim = createSimulation(WORLD);
  sim.bip.position = { x: 46.5, y: 30.5 };
  const host = { canOpen: vi.fn(() => true), open: vi.fn(() => true) };
  return { sim, host, approach: new SocialApproach(sim, host) };
}
describe('bounded social approach', () => {
  it.each(['timeout', 'authority', 'obstacle'] as const)(
    'abandons the route after %s without opening a conversation',
    reason => {
      const { sim, host, approach } = setup();
      expect(approach.start({ kind: 'lia' })).toBe(true);
      if (reason === 'timeout') sim.time = 31;
      if (reason === 'authority') host.canOpen.mockReturnValue(false);
      if (reason === 'obstacle') {
        sim.time = 0.6;
        sim.navigation.blocked.fill(1);
      }
      approach.update();
      expect(sim.player.path).toEqual([]);
      expect(host.open).not.toHaveBeenCalled();
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

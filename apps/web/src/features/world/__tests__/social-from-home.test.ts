import { describe, expect, it, vi } from 'vitest';
import { WORLD } from '../definition';
import { createSimulation, stepSimulation } from '../simulation';
import { SocialApproach } from '../social-approach';
import { objectApproaches } from '../scene-interactions';
import { findRoute } from '../navigation';

describe('introduction return from the mirror', () => {
  it('reroutes from the server-confirmed corner beside the atrium chair', () => {
    const sim = createSimulation(WORLD);
    sim.player.position = { x: 44.19, y: 42.23 };
    expect(findRoute(sim.navigation, sim.player.position, WORLD.bipSpawn).length).toBeGreaterThan(
      0
    );
    const host = { canOpen: () => true, open: vi.fn(() => true) };
    expect(new SocialApproach(sim, host).start({ kind: 'lia' })).toBe(true);
  });
  it.each([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60])(
    'can reach the patrolling companion after a native activity at phase %s',
    phase => {
      const sim = createSimulation(WORLD);
      for (let n = 0; n < phase * 60; n++) stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
      const mirror = WORLD.props.find(prop => prop.key === 'appearance')!;
      const goal = objectApproaches(mirror, WORLD.spawn).find(
        point => findRoute(sim.navigation, WORLD.spawn, point).length
      )!;
      expect(goal).toBeDefined();
      sim.player.position = { ...goal };
      const host = { canOpen: () => true, open: vi.fn(() => true) };
      const approach = new SocialApproach(sim, host);
      expect(approach.start({ kind: 'lia' })).toBe(true);
      for (let n = 0; n < 1800 && !host.open.mock.calls.length; n++) {
        stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
        approach.update();
      }
      expect(
        host.open,
        JSON.stringify({
          player: sim.player.position,
          lia: sim.bip.position,
          path: sim.player.path,
        })
      ).toHaveBeenCalledOnce();
    }
  );
});

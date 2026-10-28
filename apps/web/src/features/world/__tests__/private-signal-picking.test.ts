import { afterEach, expect, it, vi } from 'vitest';
import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { WORLD } from '../definition';
import { hitsPrivateSignal, privateSignalBounds } from '../art/private-signals';
import { project, unproject } from '../geometry';
import { WorldPropIndex } from '../prop-index';
import { WorldRenderer } from '../renderer';
import { createSimulation } from '../simulation';
afterEach(() => vi.restoreAllMocks());
it('keeps every badge inside the indexed art bounds and excludes its transparent corners', () => {
  const index = new WorldPropIndex(WORLD.props);
  for (const prop of WORLD.props.filter(prop => prop.height >= 0.1)) {
    const b = privateSignalBounds(prop);
    const center = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
    expect(index.query({ ...center, width: 1, height: 1 })).toContain(prop);
    expect(hitsPrivateSignal(prop, center)).toBe(true);
    expect(hitsPrivateSignal(prop, { x: b.x, y: b.y })).toBe(false);
    expect(hitsPrivateSignal(prop, { x: b.x - 1, y: center.y })).toBe(false);
  }
  index.clear();
});
it('picks a visible badge through transparent art and forgets it on withdrawal and destruction', () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    canvasContext({
      getImageData: () => ({
        data: new Uint8ClampedArray(4),
        width: 1,
        height: 1,
        colorSpace: 'srgb',
      }),
    })
  );
  const prop = WORLD.props.find(item => item.key === 'sms-stand');
  if (!prop) throw new Error('Missing authored SMS stand');
  const world = { ...WORLD, props: [prop] };
  const sim = createSimulation(world);
  sim.player.position = sim.bip.position = { x: -1000, y: -1000 };
  const renderer = new WorldRenderer(document.createElement('canvas'), world, 'low', {
    player: 'Me',
    bip: 'LIA',
  });
  const b = privateSignalBounds(prop);
  const point = unproject({ x: b.x + 12, y: b.y + 10 });
  expect(project(point).x).toBeCloseTo(b.x + 12);
  expect(project(point).y).toBeCloseTo(b.y + 10);
  renderer.setPrivateSignals([{ propId: prop.id, kind: 'sms', status: 'ready', count: 1 }]);
  expect(renderer.pick(point, sim)).toEqual({ kind: 'object', id: prop.id });
  renderer.setPrivateSignals([]);
  expect(renderer.pick(point, sim)).toBeNull();
  renderer.destroy();
  renderer.setPrivateSignals([{ propId: prop.id, kind: 'sms', status: 'ready', count: 1 }]);
  expect(renderer.pick(point, sim)).toBeNull();
});

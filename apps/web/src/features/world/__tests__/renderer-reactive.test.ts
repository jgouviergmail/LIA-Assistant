import { afterEach, expect, it, vi } from 'vitest';
import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { WORLD } from '../definition';
import { WorldRenderer } from '../renderer';
import { createSimulation } from '../simulation';
import { createCamera } from '../geometry';
import type { Season } from '../season';
import * as art from '../art/props';
import * as style from '../art/prop-style';
afterEach(() => vi.restoreAllMocks());
it('keeps sheltered foliage green while the same outdoor plant follows autumn', () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext({}));
  const plant = WORLD.props.find(prop => prop.kind === 'plant');
  const room = WORLD.zones.find(zone => zone.covered);
  if (!plant || !room) throw new Error('Missing authored foliage');
  const inside = { ...plant, id: 'inside', x: 3, y: 3 };
  const outside = { ...plant, id: 'outside', x: 11, y: 3 };
  const world = {
    ...WORLD,
    width: 16,
    height: 8,
    props: [inside, outside],
    grounds: [],
    zones: [{ ...room, x: 0, y: 0, width: 8, height: 8 }],
  };
  const sim = createSimulation(world);
  sim.player.position = sim.bip.position = { x: -1000, y: -1000 };
  const paint = vi.spyOn(art, 'paintProp');
  const renderer = new WorldRenderer(document.createElement('canvas'), world, 'low', {
    player: '',
    bip: '',
  });
  renderer.setSeason('autumn');
  renderer.render(createCamera({ width: 1000, height: 700 }, { x: 7, y: 3 }), sim);
  expect(paint.mock.calls.find(([prop]) => prop.id === 'inside')?.[3]).toBe('neutral');
  expect(paint.mock.calls.find(([prop]) => prop.id === 'outside')?.[3]).toBe('autumn');
  renderer.destroy();
});
it('activates only visible current decor, preserves geometry and bounds texture retention across seasonal changes', () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext({}));
  const authored = WORLD.props.find(prop => prop.kind === 'plant');
  if (!authored) throw new Error('Missing plant');
  const prop = { ...authored, x: 3, y: 3 };
  const world = { ...WORLD, width: 8, height: 8, props: [prop], zones: [], grounds: [] };
  const original = JSON.stringify(world);
  const sim = createSimulation(world);
  sim.player.position = sim.bip.position = { x: -1000, y: -1000 };
  const camera = createCamera({ width: 800, height: 600 }, prop);
  const renderer = new WorldRenderer(document.createElement('canvas'), world, 'low', {
    player: 'You',
    bip: 'LIA',
  });
  renderer.render(camera, sim);
  expect(renderer.cosmeticTarget(prop.id)).toMatchObject({ id: prop.id, action: 'plant' });
  expect(renderer.activateCosmetic(prop.id, camera, sim)).toBe(true);
  expect(renderer.activateCosmetic(prop.id, camera, sim)).toBe(false);
  expect(renderer.activateCosmetic('invented', camera, sim)).toBe(false);
  let largest = 0;
  const seasons: Season[] = ['spring', 'summer', 'autumn', 'winter', 'neutral'];
  for (let i = 0; i < 40; i++) {
    renderer.setSeason(seasons[i % seasons.length]);
    renderer.render(camera, sim);
    largest = Math.max(largest, renderer.textureBytes);
  }
  expect(largest).toBeLessThan(2 * 1024 * 1024);
  camera.center = { x: -10000, y: -10000 };
  expect(renderer.activateCosmetic(prop.id, camera, sim)).toBe(false);
  expect(JSON.stringify(world)).toBe(original);
  renderer.destroy();
  expect(renderer.textureBytes).toBe(0);
  expect(renderer.activateCosmetic(prop.id, camera, sim)).toBe(false);
});
it('releases private seasonal surfaces when a home palette changes', () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext({}));
  const plant = WORLD.props.find(prop => prop.kind === 'plant');
  const home = WORLD.zones.find(zone => zone.id === 'home');
  if (!plant || !home) throw new Error('Missing authored art');
  const prop = { ...plant, x: 3, y: 3 };
  const world = {
    ...WORLD,
    width: 8,
    height: 8,
    props: [prop],
    grounds: [],
    zones: [{ ...home, x: 0, y: 0, width: 8, height: 8 }],
  };
  const sim = createSimulation(world);
  sim.player.position = sim.bip.position = { x: -1000, y: -1000 };
  const camera = createCamera({ width: 800, height: 600 }, prop);
  const renderer = new WorldRenderer(document.createElement('canvas'), world, 'low', {
    player: 'You',
    bip: 'LIA',
  });
  renderer.setSeason('spring');
  renderer.setHome({ palette: 'teal' });
  const create = vi.spyOn(document, 'createElement');
  renderer.render(camera, sim);
  const surfaces = create.mock.results.flatMap(result =>
    result.type === 'return' && result.value instanceof HTMLCanvasElement ? [result.value] : []
  );
  expect(surfaces.some(surface => surface.width > 0)).toBe(true);
  renderer.setHome({ palette: 'violet' });
  expect(surfaces.some(surface => surface.width === 0)).toBe(true);
  renderer.render(camera, sim);
  renderer.destroy();
  expect(renderer.textureBytes).toBe(0);
});
it('derives each prop texture identity once, never again on a later frame, until the season changes', () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    canvasContext({ measureText: () => ({ width: 0 }) as TextMetrics })
  );
  const sim = createSimulation(WORLD);
  const camera = createCamera({ width: 1000, height: 700 }, WORLD.spawn);
  const renderer = new WorldRenderer(document.createElement('canvas'), WORLD, 'low', {
    player: '',
    bip: '',
  });
  const keys = vi.spyOn(style, 'propTextureKey');
  renderer.render(camera, sim);
  const first = keys.mock.calls.length;
  expect(first).toBeGreaterThan(0);
  for (let frame = 0; frame < 5; frame++) renderer.render(camera, sim);
  expect(keys).toHaveBeenCalledTimes(first);
  renderer.setSeason('winter');
  renderer.render(camera, sim);
  expect(keys.mock.calls.length).toBeGreaterThan(first);
  renderer.destroy();
});

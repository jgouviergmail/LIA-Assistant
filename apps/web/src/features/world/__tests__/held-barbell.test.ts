import { afterEach, expect, it, vi } from 'vitest';
import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import * as bars from '../art/barbell';
import * as actors from '../art/props';
import { WORLD } from '../definition';
import { WorldRenderer } from '../renderer';
import { createSimulation } from '../simulation';
import { createCamera } from '../geometry';
import { compilePoseSlots } from '../pose-slots';
import { barbellModel, heldBarbellOffset } from '../art/barbell';
import { canonicalSize, orientModel } from '../art/model';
import { project } from '../geometry';
import { cosmeticDuration } from '../cosmetic-effects';
afterEach(() => vi.restoreAllMocks());
it('composes the held bar after the owner body so the far plate cannot disappear behind its torso', () => {
  const context = canvasContext({ measureText: () => ({ width: 0 }) as TextMetrics });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context);
  const slot = compilePoseSlots(WORLD).find(item => item.id === 'workout-1:0');
  if (!slot) throw new Error('Missing workout');
  const sim = createSimulation(WORLD);
  sim.player.pose = slot;
  sim.player.position = { ...slot.position };
  sim.player.facing = slot.facing;
  sim.player.heading = slot.facing * 2;
  sim.bip.position = { x: -1000, y: -1000 };
  const camera = createCamera({ width: 800, height: 600 }, slot.position);
  const renderer = new WorldRenderer(document.createElement('canvas'), WORLD, 'low', {
    player: '',
    bip: '',
  });
  const order: string[] = [];
  const props = vi.spyOn(actors, 'paintProp');
  const actor = actors.paintActor,
    held = bars.paintHeldBarbell;
  vi.spyOn(actors, 'paintActor').mockImplementation((...args) => {
    order.push('body');
    return actor(...args);
  });
  vi.spyOn(bars, 'paintHeldBarbell').mockImplementation((...args) => {
    order.push('held');
    return held(...args);
  });
  expect(renderer.activateCosmetic(slot.prop, camera, sim)).toBe(true);
  renderer.render(camera, sim);
  expect(order.indexOf('held')).toBeGreaterThan(order.indexOf('body'));
  expect(
    props.mock.calls.filter(([prop, _ratio, shadow]) => prop.id === slot.prop && shadow === false)
  ).toHaveLength(0);
  renderer.destroy();
});

function workout() {
  const context = canvasContext({ measureText: () => ({ width: 0 }) as TextMetrics });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context);
  const slot = compilePoseSlots(WORLD).find(item => item.id === 'workout-1:0');
  const prop = WORLD.props.find(item => item.key === 'workout-1');
  if (!slot || !prop) throw new Error('Missing workout');
  const sim = createSimulation(WORLD);
  sim.player.pose = slot;
  sim.player.position = { ...slot.position };
  sim.player.facing = slot.facing;
  sim.player.heading = slot.facing * 2;
  sim.bip.position = { x: -1000, y: -1000 };
  const camera = createCamera({ width: 800, height: 600 }, slot.position);
  const renderer = new WorldRenderer(document.createElement('canvas'), WORLD, 'low', {
    player: '',
    bip: '',
  });
  return { context, slot, prop, sim, camera, renderer };
}
it('paints the held bar once for a whole workout and moves that one sprite along every press', () => {
  let now = 1000;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const { context, slot, sim, camera, renderer } = workout();
  const paints: HTMLCanvasElement[] = [];
  const held = bars.paintHeldBarbell;
  vi.spyOn(bars, 'paintHeldBarbell').mockImplementation((...args) => {
    const sprite = held(...args);
    paints.push(sprite.canvas);
    return sprite;
  });
  expect(renderer.activateCosmetic(slot.prop, camera, sim)).toBe(true);
  const duration = cosmeticDuration('workout');
  for (let frame = 0; frame * (1000 / 60) < duration; frame++) {
    now = 1000 + frame * (1000 / 60);
    renderer.render(camera, sim);
  }
  // One sprite for the whole workout: every frame is a cache hit after the first paint.
  expect(paints).toHaveLength(1);
  const drawn = vi
    .mocked(context.drawImage)
    .mock.calls.filter(([image]) => image === paints[0])
    .map(([, x, y]) => `${x}:${y}`);
  expect(new Set(drawn).size).toBeGreaterThan(10);
  renderer.destroy();
});
it('offsets the racked sprite exactly where a lift would have painted the bar', () => {
  const prop = WORLD.props.find(item => item.key === 'workout-1');
  if (!prop) throw new Error('Missing workout');
  const { w, d } = canonicalSize(prop);
  const shaft = (press: number, barReach: number) => {
    const part = orientModel(barbellModel(w, { press, barReach }), w, d, prop.facing ?? 1)[0];
    if (part.kind !== 'box') throw new Error('Missing shaft');
    return project(part, part.z);
  };
  const racked = shaft(0, 0);
  for (const [press, barReach] of [
    [0, 0.5],
    [0, 1],
    [0.5, 1],
    [1, 1],
  ]) {
    const offset = heldBarbellOffset(prop, { press, barReach });
    const lifted = shaft(press, barReach);
    expect(racked.x + offset.x).toBeCloseTo(lifted.x, 9);
    expect(racked.y + offset.y).toBeCloseTo(lifted.y, 9);
  }
});

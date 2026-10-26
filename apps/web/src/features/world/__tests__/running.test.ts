import { afterEach, expect, it, vi } from 'vitest';
import { createInput } from '../input';
import { createCamera } from '../geometry';
import { WORLD } from '../definition';
import { createSimulation, stepSimulation, walkTo } from '../simulation';
afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});
it('runs only on a deliberate nearby double tap, and never carries that gesture across a drag or blur', () => {
  const canvas = document.createElement('canvas');
  canvas.tabIndex = 0;
  document.body.append(canvas);
  const walk = vi.fn(),
    input = createInput(canvas, createCamera({ width: 800, height: 600 }, WORLD.spawn), {
      walk,
      changed: () => {},
    });
  let time = 1000;
  const event = (type: string, x = 100) => {
    const e = new MouseEvent(type, { clientX: x, clientY: 100, bubbles: true, cancelable: true });
    Object.defineProperties(e, { pointerId: { value: 1 }, timeStamp: { value: time } });
    canvas.dispatchEvent(e);
  };
  const tap = () => {
    event('pointerdown');
    time += 10;
    event('pointerup');
  };
  tap();
  expect(walk.mock.calls[0][1]).not.toBe(true);
  time += 180;
  tap();
  expect(walk.mock.calls[1][1]).toBe(true);
  window.dispatchEvent(new Event('blur'));
  time += 100;
  tap();
  expect(walk.mock.calls[2][1]).not.toBe(true);
  event('pointerdown');
  event('pointermove', 140);
  event('pointerup', 140);
  time += 100;
  tap();
  expect(walk.mock.lastCall?.[1]).not.toBe(true);
  input.dispose();
});
it('runs faster along the same collision-safe route and returns to walking when it ends', () => {
  const a = createSimulation(WORLD),
    b = createSimulation(WORLD);
  const goal = { x: WORLD.spawn.x, y: WORLD.spawn.y + 5 };
  expect(walkTo(a, goal)).toBe(true);
  expect(walkTo(b, goal, true)).toBe(true);
  for (let i = 0; i < 5; i++) {
    stepSimulation(a, 0.02, { x: 0, y: 0 });
    stepSimulation(b, 0.02, { x: 0, y: 0 });
  }
  expect((b.player.position.y - WORLD.spawn.y) / (a.player.position.y - WORLD.spawn.y)).toBeCloseTo(
    1.5
  );
  for (let i = 0; i < 100; i++) stepSimulation(b, 0.02, { x: 0, y: 0 });
  expect(b.player.running).toBe(false);
});

import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { CosmeticScene } from '../cosmetic-scene';
import { cosmeticPropTarget } from '../cosmetic-interactions';
import { createCamera } from '../geometry';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';
it('toggles the actual initial night light off and keeps that choice when daylight returns', () => {
  const scene = new CosmeticScene(WORLD);
  const lamp = WORLD.props.find(prop => prop.kind === 'lamp' && cosmeticPropTarget(prop));
  if (!lamp) throw new Error('Missing lamp');
  const camera = createCamera({ width: 10000, height: 10000 }, lamp);
  scene.sample(0, { ...NEUTRAL_ATMOSPHERE, phase: 'night' }, 'low', false, 0, camera, {
    x: -1000,
    y: -1000,
  });
  scene.activate(lamp.id, camera, 0, 'low');
  expect(scene.presentation(lamp.id, false).light).toBe(false);
  scene.sample(1, NEUTRAL_ATMOSPHERE, 'low', false, 1, camera, { x: -1000, y: -1000 });
  expect(scene.presentation(lamp.id, false).light).toBe(false);
  scene.activate(lamp.id, camera, 2, 'low');
  expect(scene.presentation(lamp.id, false).light).toBe(true);
});
it('toggles a lamp immediately and cycles five screen contents without mutating the world', () => {
  const scene = new CosmeticScene(WORLD);
  const lamp = WORLD.props.find(prop => prop.kind === 'lamp' && cosmeticPropTarget(prop));
  const screen = WORLD.props.find(prop => prop.kind === 'display' && cosmeticPropTarget(prop));
  if (!lamp || !screen) throw new Error('Missing authored decor');
  const original = JSON.stringify(WORLD);
  const camera = createCamera({ width: 10000, height: 10000 }, lamp);
  scene.sample(0, NEUTRAL_ATMOSPHERE, 'low', false, 0, camera, { x: -1000, y: -1000 });
  expect(scene.activate(lamp.id, camera, 0, 'low')).toBe(true);
  expect(scene.presentation(lamp.id, false).light).toBe(true);
  expect(scene.activate(lamp.id, camera, 1, 'low')).toBe(true);
  expect(scene.presentation(lamp.id, false).light).toBe(false);
  for (const variant of [1, 2, 3, 4, 0]) {
    expect(scene.activate(screen.id, camera, 2, 'low')).toBe(true);
    expect(scene.presentation(screen.id, false).screen).toBe(variant);
  }
  expect(scene.target('ambient-bird-0')).toBeNull();
  for (const flower of WORLD.props.filter(prop => prop.kind === 'flowers'))
    expect(scene.target(flower.id)).toBeNull();
  scene.clear();
  expect(scene.presentation(lamp.id, false).light).toBeUndefined();
  expect(JSON.stringify(WORLD)).toBe(original);
});

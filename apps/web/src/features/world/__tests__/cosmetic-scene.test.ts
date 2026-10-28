import { expect, it } from 'vitest';
import { CosmeticScene } from '../cosmetic-scene';
import { WORLD } from '../definition';
import { createCamera, project } from '../geometry';
import { ambientLifeAt, catAt } from '../world-life';
import { reactionAmount } from '../art/reactive-decor';
import type { Atmosphere } from '../atmosphere';
const atmosphere: Atmosphere = {
  phase: 'afternoon',
  weather: 'neutral',
  sunny: true,
  time: null,
  timezone: null,
};
it('reacts once to a real fauna approach, waits for departure and reentry, and respects reduced motion', () => {
  const agent = ambientLifeAt(WORLD, atmosphere, 0, 'balanced', false)[0];
  const camera = createCamera({ width: 800, height: 600 }, agent.point);
  const scene = new CosmeticScene(WORLD);
  scene.sample(0, atmosphere, 'balanced', false, 0, camera, agent.point);
  expect(scene.frames.has(agent.id)).toBe(true);
  scene.sample(0, atmosphere, 'balanced', false, 2100, camera, agent.point);
  expect(scene.frames.has(agent.id)).toBe(false);
  scene.sample(0, atmosphere, 'balanced', false, 2400, camera, { x: -1000, y: -1000 });
  scene.sample(0, atmosphere, 'balanced', false, 2700, camera, agent.point);
  expect(scene.frames.has(agent.id)).toBe(true);
  scene.sample(0, atmosphere, 'balanced', true, 3000, camera, agent.point);
  expect(scene.life).toEqual([]);
  expect(scene.frames.has(agent.id)).toBe(false);
});
it('turns the local cat briefly, restores its patrol and never adds collision geometry', () => {
  const cat = catAt(WORLD, 0);
  if (!cat) throw new Error('Missing cat');
  const original = JSON.stringify(WORLD);
  const camera = createCamera({ width: 800, height: 600 }, cat);
  const scene = new CosmeticScene(WORLD);
  scene.sample(0, atmosphere, 'balanced', false, 0, camera, { x: -1000, y: -1000 });
  expect(scene.activate(cat.id, camera, 0, 'balanced')).toBe(true);
  scene.sample(0, atmosphere, 'balanced', false, 300, camera, { x: -1000, y: -1000 });
  expect(scene.cat?.facing).not.toBe(cat.facing);
  scene.sample(0, atmosphere, 'balanced', false, 1700, camera, { x: -1000, y: -1000 });
  expect(scene.cat).toEqual(cat);
  expect(JSON.stringify(WORLD)).toBe(original);
  scene.clear();
  expect(scene.frames.size).toBe(0);
});
it('bounds anticipation, response and settling without integrating displacement', () => {
  expect(reactionAmount(0)).toBe(0);
  expect(reactionAmount(0.04)).toBeLessThan(0);
  expect(reactionAmount(0.25)).toBeGreaterThan(0);
  for (let step = 0; step <= 1000; step++)
    expect(Math.abs(reactionAmount(step / 1000))).toBeLessThanOrEqual(1);
  expect(reactionAmount(1)).toBe(0);
  expect(reactionAmount(100)).toBe(0);
});
it('picks the butterfly at its painted response position and forgets expired motion', () => {
  const butterfly = ambientLifeAt(WORLD, atmosphere, 0, 'balanced', false).find(
    agent => agent.action === 'butterfly'
  );
  if (!butterfly) throw new Error('Missing butterfly');
  const scene = new CosmeticScene(WORLD);
  const camera = createCamera({ width: 800, height: 600 }, butterfly.point);
  const far = { x: -1000, y: -1000 };
  scene.sample(0, atmosphere, 'balanced', false, 0, camera, far);
  expect(scene.activate(butterfly.id, camera, 0, 'balanced')).toBe(true);
  expect(scene.activate('unknown', camera, 0, 'balanced')).toBe(false);
  scene.sample(0, atmosphere, 'balanced', false, 800, camera, far);
  const rest = project(butterfly.point, butterfly.elevation);
  const moving = { x: rest.x + 15, y: rest.y - 4 };
  expect(scene.pickLife(moving)).toBe(butterfly.id);
  expect(scene.pickLife(rest)).not.toBe(butterfly.id);
  expect(scene.reaction(butterfly.id, false)).toBe(0);
  expect(scene.reaction('unknown', false)).toBe(0);
  scene.sample(0, atmosphere, 'balanced', false, 2000, camera, far);
  expect(scene.pickLife(rest)).toBe(butterfly.id);
});
it('round-trips only authored local lamp and screen appearance, clears it on destruction and cancels an active reaction', () => {
  const lamp = WORLD.props.find(prop => prop.kind === 'lamp');
  const screen = WORLD.props.find(prop => prop.kind === 'display');
  const machine = WORLD.props.find(prop => prop.kind === 'machine');
  if (!lamp || !screen || !machine) throw new Error('Missing authored decor');
  const scene = new CosmeticScene(WORLD, [
    { id: lamp.id, light: true },
    { id: screen.id, screen: 3 },
    { id: 'foreign', light: true },
  ]);
  expect(scene.light(lamp.id)).toBe(true);
  expect(scene.hasLight()).toBe(true);
  expect(scene.photoDecor()).toEqual([
    { id: lamp.id, light: true },
    { id: screen.id, screen: 3 },
  ]);
  const restored = new CosmeticScene(WORLD, scene.photoDecor());
  expect(restored.presentation(screen.id, false)).toEqual({ id: screen.id, screen: 3 });
  const camera = createCamera({ width: 800, height: 600 }, machine);
  expect(scene.activate(machine.id, camera, 0, 'balanced')).toBe(true);
  scene.sample(0, atmosphere, 'balanced', false, 600, camera, machine);
  expect(scene.presentation(machine.id, false).machine).toBeGreaterThan(0);
  expect(scene.presentation(machine.id, true).machine).toBe(0.5);
  scene.cancel(machine.id);
  scene.sample(0, atmosphere, 'balanced', false, 800, camera, machine);
  expect(scene.frames.has(machine.id)).toBe(false);
  expect(scene.presentation(machine.id, false)).toEqual({});
  scene.clear();
  expect(scene.hasLight()).toBe(false);
  expect(scene.photoDecor()).toEqual([]);
  expect(scene.light(lamp.id)).toBeUndefined();
});
it('projects a reduced workout safely and refuses painted or clickable state for removed targets and ambient birds', () => {
  const prop = WORLD.props.find(item => item.key === 'workout-1');
  if (!prop) throw new Error('Missing workout');
  const scene = new CosmeticScene(WORLD);
  const camera = createCamera({ width: 800, height: 600 }, prop);
  expect(scene.activate(prop.id, camera, 0, 'low')).toBe(true);
  scene.sample(0, atmosphere, 'low', false, 1800, camera, prop);
  expect(scene.presentation(prop.id, true)).toMatchObject({ press: 0.5, barReach: 1 });
  expect(scene.presentation(prop.id, false).press).toBeGreaterThan(0);
  scene.effects.activate(
    { id: 'removed', action: 'plant', point: prop, elevation: 0 },
    1800,
    true,
    'balanced'
  );
  scene.sample(0, atmosphere, 'balanced', false, 1900, camera, prop);
  expect(scene.frames.has('removed')).toBe(false);
  const bird = scene.life.find(agent => agent.action === 'bird');
  if (!bird) throw new Error('Missing ambient bird');
  expect(scene.target(bird.id)).toBeNull();
  expect(scene.pickLife(project(bird.point, bird.elevation))).not.toBe(bird.id);
});
it('lights the evening only for a lamp switched on, never for one switched off or a screen', () => {
  const lamp = WORLD.props.find(prop => prop.kind === 'lamp');
  const screen = WORLD.props.find(prop => prop.kind === 'display');
  if (!lamp || !screen) throw new Error('Missing authored decor');
  const scene = new CosmeticScene(WORLD, [
    { id: lamp.id, light: false },
    { id: screen.id, screen: 2 },
  ]);
  expect(scene.hasLight()).toBe(false);
  expect(scene.light(lamp.id)).toBe(false);
  expect(new CosmeticScene(WORLD, [{ id: lamp.id, light: true }]).hasLight()).toBe(true);
});
it('sways a touched plant with full motion and holds it still under reduced motion', () => {
  const plant = WORLD.props.find(prop => prop.kind === 'plant');
  if (!plant) throw new Error('Missing authored plant');
  const scene = new CosmeticScene(WORLD);
  const camera = createCamera({ width: 800, height: 600 }, plant);
  expect(scene.activate(plant.id, camera, 0, 'balanced')).toBe(true);
  scene.sample(0, atmosphere, 'balanced', false, 400, camera, plant);
  expect(scene.reaction(plant.id, false)).not.toBe(0);
  expect(scene.reaction(plant.id, true)).toBe(0);
});

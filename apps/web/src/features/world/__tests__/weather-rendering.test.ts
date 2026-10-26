import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { paintPondMotion } from '../art/pond-motion';
import { expect, it, vi } from 'vitest';
import { paintAtmosphere, paintGroundShade } from '../art/atmosphere';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';
import { WORLD } from '../definition';
import { createCamera } from '../geometry';
import type { Ground, WorldDefinition, WorldProp } from '../types';
const camera = createCamera({ width: 100, height: 80 }, { x: 5, y: 5 });
function context() {
  return canvasContext({
    save: vi.fn(),
    restore: vi.fn(),
    translate: vi.fn(),
    scale: vi.fn(),
    fillRect: vi.fn(),
    drawImage: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    arc: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    rect: vi.fn(),
    closePath: vi.fn(),
    clip: vi.fn(),
    ellipse: vi.fn(),
  });
}
function scene(ground: Ground, covered: boolean): WorldDefinition {
  return {
    ...WORLD,
    props: [],
    grounds: [{ x: -100, y: -100, width: 200, height: 200, kind: ground }],
    zones: covered
      ? [{ ...WORLD.zones[0], x: -100, y: -100, width: 200, height: 200, covered: true }]
      : [],
  };
}
it('windows never emit halos; only the actual lamp is a luminous source', () => {
  const c = context();
  const prop = (kind: WorldProp['kind'], wallFinish: WorldProp['wallFinish']): WorldProp => ({
    id: kind + wallFinish,
    kind,
    wallFinish,
    x: 5,
    y: 5,
    width: 1,
    depth: 1,
    height: 3,
    tone: 'sage',
    blocking: false,
  });
  const world = {
    ...scene('tile', false),
    props: [
      prop('lamp', undefined),
      prop('window', 'acoustic'),
      prop('sideWindow', 'glass'),
      prop('window', 'oak'),
      prop('sideWindow', 'plaster'),
    ],
  };
  const glow = {
    canvas: document.createElement('canvas'),
    width: 160,
    height: 100,
    anchorX: 80,
    anchorY: 50,
  };
  paintAtmosphere(
    c,
    world,
    camera,
    { ...NEUTRAL_ATMOSPHERE, phase: 'night' },
    0,
    'balanced',
    true,
    glow
  );
  expect(c.drawImage).toHaveBeenCalledTimes(1);
});
for (const weather of ['rain', 'snow'] as const) {
  for (const ground of ['tile', 'path', 'deck', 'wood'] as const) {
    it(
      weather + ' respects shelter on ' + ground + ' without mistaking an exposed floor for a roof',
      () => {
        const c = context();
        const render = (covered: boolean) =>
          paintAtmosphere(
            c,
            scene(ground, covered),
            camera,
            { ...NEUTRAL_ATMOSPHERE, weather },
            1,
            'balanced',
            false,
            null
          );
        render(true);
        expect(c.lineTo).not.toHaveBeenCalled();
        expect(c.arc).not.toHaveBeenCalled();
        render(false);
        expect(weather === 'rain' ? c.lineTo : c.arc).toHaveBeenCalled();
      }
    );
  }
}

it('bounds pond animation work and completely suppresses it for reduced motion', () => {
  const c = context(),
    world = {
      ...scene('grass', false),
      grounds: [{ x: 3, y: 3, width: 4, height: 4, kind: 'water' as const }],
    };
  paintPondMotion(c, world, camera, 1, 'high', true);
  expect(c.ellipse).not.toHaveBeenCalled();
  paintPondMotion(c, world, camera, 1, 'low', false);
  expect(c.ellipse).toHaveBeenCalledTimes(2);
});

it('leaves daylight untouched and layers gentle indoor and stronger outdoor night tint', () => {
  const c = context(),
    world = scene('wood', true);
  paintGroundShade(c, world, camera, NEUTRAL_ATMOSPHERE);
  expect(c.fillRect).not.toHaveBeenCalled();
  paintGroundShade(c, world, camera, {
    ...NEUTRAL_ATMOSPHERE,
    phase: 'night',
  });
  expect(c.clip).toHaveBeenCalledWith('evenodd');
  expect(c.rect).toHaveBeenCalledWith(0, 0, camera.width, camera.height);
  expect(c.closePath).toHaveBeenCalledTimes(world.zones.length + 1);
  expect(c.fillRect).toHaveBeenCalledWith(0, 0, camera.width, camera.height);
  expect(c.restore).toHaveBeenCalledOnce();
});

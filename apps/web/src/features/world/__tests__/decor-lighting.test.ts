import { expect, it, vi } from 'vitest';
import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { paintAtmosphere, paintGroundLights } from '../art/atmosphere';
import { WORLD } from '../definition';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';
import { createCamera } from '../geometry';
it('lights an explicitly enabled lamp by day, suppresses an off lamp at night and never gives a window a halo', () => {
  const lamp = WORLD.props.find(prop => prop.kind === 'lamp');
  if (!lamp) throw new Error('Missing authored lamp');
  const window = { ...lamp, id: 'window-fixture', kind: 'window' as const, x: lamp.x + 2 };
  const world = { ...WORLD, props: [lamp, window] },
    camera = createCamera({ width: 1000, height: 800 }, lamp);
  const drawImage = vi.fn(),
    c = canvasContext({ drawImage });
  const glow = {
    canvas: document.createElement('canvas'),
    width: 64,
    height: 64,
    anchorX: 32,
    anchorY: 32,
  };
  const paint = (phase: 'noon' | 'night', state?: boolean) => {
    paintGroundLights(c, world, camera, { ...NEUTRAL_ATMOSPHERE, phase }, glow, id =>
      id === lamp.id ? state : undefined
    );
    paintAtmosphere(c, world, camera, { ...NEUTRAL_ATMOSPHERE, phase }, 0, 'low', true, glow, id =>
      id === lamp.id ? state : undefined
    );
  };
  paint('noon');
  expect(drawImage).not.toHaveBeenCalled();
  paint('noon', true);
  expect(drawImage).toHaveBeenCalledTimes(2);
  drawImage.mockClear();
  paint('night', false);
  expect(drawImage).not.toHaveBeenCalled();
  paint('night');
  expect(drawImage).toHaveBeenCalledTimes(2);
});

import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { afterEach, expect, it, vi } from 'vitest';
import { WorldRenderer } from '../renderer';
import { createCamera, project } from '../geometry';
import { createSimulation } from '../simulation';
import { WORLD } from '../definition';
import type { LiaAtlas } from '../art/lia-atlas';

const art = vi.hoisted(() => ({ actor: vi.fn() }));
vi.mock('../art/props', () => ({
  paintActor: () => {
    art.actor();
    return {
      canvas: document.createElement('canvas'),
      width: 64,
      height: 100,
      anchorX: 32,
      anchorY: 90,
    };
  },
  paintProp: vi.fn(),
}));
vi.mock('../art/floors', () => ({
  paintFloor: () => ({
    canvas: document.createElement('canvas'),
    width: 64,
    height: 32,
    anchorX: 32,
    anchorY: 0,
  }),
}));
vi.mock('../art/lia-atlas', () => ({
  LiaAtlas: class implements Pick<LiaAtlas, keyof LiaAtlas> {
    prepareImage() {
      return Promise.resolve();
    }
    textureBytes = 0;
    setVisible() {}
    setActing() {}
    draw() {
      return false;
    }
    destroy() {}
  },
}));
vi.mock('../art/atmosphere', () => ({
  paintGroundShade: vi.fn(),
  paintGroundLights: vi.fn(),
  paintAtmosphere: vi.fn(),
  paintLampGlow: vi.fn(),
}));
vi.mock('../art/ambient-life', () => ({ paintAmbientLife: vi.fn() }));
vi.mock('../art/pond-motion', () => ({ paintPondMotion: vi.fn() }));
vi.mock('../world-life', async importOriginal => ({
  ...(await importOriginal<typeof import('../world-life')>()),
  catAt: () => null,
}));

afterEach(() => {
  vi.restoreAllMocks();
  art.actor.mockClear();
});
it('skips offscreen actor artwork and mask preparation but keeps partially visible heads', () => {
  const context = canvasContext({
    measureText: () => ({
      width: 30,
      actualBoundingBoxAscent: 0,
      actualBoundingBoxDescent: 0,
      actualBoundingBoxLeft: 0,
      actualBoundingBoxRight: 30,
      alphabeticBaseline: 0,
      emHeightAscent: 0,
      emHeightDescent: 0,
      fontBoundingBoxAscent: 0,
      fontBoundingBoxDescent: 0,
      hangingBaseline: 0,
      ideographicBaseline: 0,
    }),
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context);
  const scene = { ...WORLD, width: 1, height: 1, props: [], zones: [], grounds: [] };
  const sim = createSimulation(scene);
  sim.player.position = { x: 10, y: 10 };
  sim.bip.position = { x: 50, y: 50 };
  const camera = createCamera({ width: 100, height: 100 }, { x: 10, y: 10 });
  camera.center = { x: -10000, y: -10000 };
  const renderer = new WorldRenderer(document.createElement('canvas'), scene, 'low', {
    player: 'You',
    bip: 'LIA',
  });
  renderer.render(camera, sim);
  expect(art.actor).not.toHaveBeenCalled();
  camera.center = project(sim.player.position);
  camera.center.y -= 120;
  renderer.render(camera, sim);
  expect(art.actor).toHaveBeenCalledTimes(1);
  renderer.destroy();
});

it.each([
  [1920, 1080],
  [3440, 1440],
])('reuses every visible floor surface at %i × %i and frees it on departure', (width, height) => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext({}));
  const scene = { ...WORLD, props: [], zones: [], grounds: [] };
  const sim = createSimulation(scene);
  sim.player.position = sim.bip.position = { x: -10000, y: -10000 };
  const camera = createCamera({ width, height }, { x: scene.width / 2, y: scene.height / 2 });
  camera.zoom = 0.55;
  const renderer = new WorldRenderer(document.createElement('canvas'), scene, 'low', {
    player: 'You',
    bip: 'LIA',
  });
  const create = vi.spyOn(document, 'createElement');
  renderer.render(camera, sim);
  const surfaces = create.mock.results.flatMap(result =>
    result.type === 'return' && result.value instanceof HTMLCanvasElement ? [result.value] : []
  );
  expect(surfaces.length).toBeGreaterThan(64);
  create.mockClear();
  renderer.render(camera, sim);
  expect(create).not.toHaveBeenCalled();
  expect(surfaces.every(surface => surface.width > 0)).toBe(true);
  camera.center = { x: -100000, y: -100000 };
  renderer.render(camera, sim);
  expect(surfaces.filter(surface => surface.width === 0).length).toBeGreaterThan(64);
  renderer.destroy();
});

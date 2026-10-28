import { afterEach, expect, it, vi } from 'vitest';
import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { drawPhotoScene } from '../photo-renderer';
import { WorldRenderer } from '../renderer';
import { projectPhotoScene } from '../photo-projection';
import { createSimulation } from '../simulation';
import { createCamera } from '../geometry';
import { WORLD } from '../definition';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';

afterEach(() => vi.restoreAllMocks());
it('builds a separate two-actor simulation and never advances or renders the live scene', async () => {
  const original = createSimulation(WORLD);
  original.player.label = 'PRIVATE_NAME';
  original.bip.label = 'PRIVATE_LIA_CONTEXT';
  original.time = 42;
  const still = projectPhotoScene({
    player: original.player,
    bip: original.bip,
    camera: createCamera({ width: 1280, height: 800 }, WORLD.spawn),
    time: original.time,
    season: 'winter',
    atmosphere: { ...NEUTRAL_ATMOSPHERE, timezone: 'PRIVATE_ZONE' },
    home: null,
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    canvasContext({ measureText: () => ({ width: 140 }) as TextMetrics })
  );
  vi.spyOn(WorldRenderer.prototype, 'preparePhoto').mockResolvedValue();
  const render = vi.spyOn(WorldRenderer.prototype, 'render').mockImplementation(() => {});
  const surface = await drawPhotoScene(
    still,
    { width: 1600, height: 900 },
    new AbortController().signal
  );
  const [camera, scene] = render.mock.calls[0];
  expect(scene).not.toBe(original);
  expect(scene.player).not.toBe(original.player);
  expect(scene.visitors).toEqual([]);
  expect(scene.player.path).toEqual([]);
  expect(JSON.stringify(scene)).not.toContain('PRIVATE_');
  expect(camera.width).toBe(1600);
  expect(camera.height).toBe(900);
  expect(original.time).toBe(42);
  expect(original.player.label).toBe('PRIVATE_NAME');
  surface.dispose();
  expect(surface.canvas.width).toBe(1);
});
it('paints only a fixed wordmark and destroys a renderer whose asset preparation fails', async () => {
  const original = createSimulation(WORLD);
  const still = projectPhotoScene({
    player: original.player,
    bip: original.bip,
    camera: createCamera({ width: 1280, height: 800 }, WORLD.spawn),
    time: 42,
    season: 'neutral',
    atmosphere: NEUTRAL_ATMOSPHERE,
    home: null,
  });
  const fillText = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    canvasContext({ fillText, measureText: () => ({ width: 140 }) as TextMetrics })
  );
  vi.spyOn(WorldRenderer.prototype, 'render').mockImplementation(() => {});
  const prepare = vi.spyOn(WorldRenderer.prototype, 'preparePhoto').mockResolvedValue();
  const destroyed = vi.spyOn(WorldRenderer.prototype, 'destroy');
  const surface = await drawPhotoScene(
    still,
    { width: 1600, height: 900 },
    new AbortController().signal
  );
  expect(fillText.mock.calls.map(([text]) => text)).toEqual([
    'LIA World - https://lia.jeyswork.com',
  ]);
  surface.dispose();
  prepare.mockRejectedValueOnce(new Error('asset'));
  await expect(
    drawPhotoScene(still, { width: 1280, height: 1600 }, new AbortController().signal)
  ).rejects.toThrow('asset');
  expect(destroyed).toHaveBeenCalledTimes(2);
});

it.each([0.55, 1.8])(
  'preserves zoom %s by cropping instead of widening a mobile viewport',
  async zoom => {
    const sim = createSimulation(WORLD);
    const camera = { ...createCamera({ width: 390, height: 844 }, WORLD.spawn), zoom };
    const still = projectPhotoScene({
      player: sim.player,
      bip: sim.bip,
      camera,
      time: 42,
      season: 'autumn',
      atmosphere: NEUTRAL_ATMOSPHERE,
      home: null,
    });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      canvasContext({ measureText: () => ({ width: 140 }) as TextMetrics })
    );
    vi.spyOn(WorldRenderer.prototype, 'preparePhoto').mockResolvedValue();
    const render = vi.spyOn(WorldRenderer.prototype, 'render').mockImplementation(() => {});
    const surface = await drawPhotoScene(
      still,
      { width: 1600, height: 900 },
      new AbortController().signal
    );
    const actual = render.mock.calls[0][0];
    expect(actual.zoom).toBeCloseTo((zoom * 1600) / 390);
    expect(actual.center).toEqual(camera.center);
    expect(actual.width / actual.zoom).toBeCloseTo(camera.width / zoom, 8);
    surface.dispose();
  }
);

it.each([0.5, 3])(
  'renders the real still at exactly the requested pixels and signs it untransformed (density %s)',
  async density => {
    const sim = createSimulation(WORLD);
    sim.player.label = 'PRIVATE_NAME';
    const still = projectPhotoScene({
      player: sim.player,
      bip: sim.bip,
      camera: createCamera({ width: 1280, height: 800 }, WORLD.spawn),
      time: 42,
      season: 'neutral',
      atmosphere: NEUTRAL_ATMOSPHERE,
      home: null,
    });
    vi.spyOn(window, 'devicePixelRatio', 'get').mockReturnValue(density);
    const context = canvasContext({ measureText: () => ({ width: 140 }) as TextMetrics });
    const fillText = vi.spyOn(context, 'fillText');
    const setTransform = vi.spyOn(context, 'setTransform');
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context);
    vi.spyOn(WorldRenderer.prototype, 'preparePhoto').mockResolvedValue();
    const surface = await drawPhotoScene(
      still,
      { width: 1600, height: 900 },
      new AbortController().signal
    );
    expect(surface.canvas.width).toBe(1600);
    expect(surface.canvas.height).toBe(900);
    const texts = fillText.mock.calls.map(([text]) => text);
    expect(texts.at(-1)).toBe('LIA World - https://lia.jeyswork.com');
    expect(texts.some(text => text.includes('PRIVATE_NAME'))).toBe(false);
    // The last transform set before the signature is the identity, in device pixels.
    const signed = fillText.mock.invocationCallOrder.at(-1) ?? Infinity;
    const before = setTransform.mock.invocationCallOrder.filter(order => order < signed).length;
    expect(setTransform.mock.calls[before - 1]).toEqual([1, 0, 0, 1, 0, 0]);
    expect(vi.mocked(context.drawImage)).toHaveBeenCalled();
    surface.dispose();
  }
);

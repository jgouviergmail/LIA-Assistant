import { afterEach, expect, it, vi } from 'vitest';
import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import {
  renderPhoto,
  photoSize,
  MAX_PHOTO_BYTES,
  PHOTO_ENCODE_TIMEOUT_MS,
  shareWorldPhoto,
} from '../photo-export';
import { drawPhotoScene } from '../photo-renderer';
import { projectPhotoScene } from '../photo-projection';
import { createSimulation } from '../simulation';
import { WORLD } from '../definition';
import { createCamera } from '../geometry';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';

vi.mock('../photo-renderer', () => ({ drawPhotoScene: vi.fn() }));
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
function scene() {
  const sim = createSimulation(WORLD);
  return projectPhotoScene({
    player: sim.player,
    bip: sim.bip,
    camera: createCamera({ width: 1280, height: 800 }, WORLD.spawn),
    time: 0,
    season: 'neutral',
    atmosphere: NEUTRAL_ATMOSPHERE,
    home: null,
  });
}
function setup(blobs: (Blob | null)[]) {
  const canvas = document.createElement('canvas');
  canvas.width = 1600;
  canvas.height = 900;
  const dispose = vi.fn();
  vi.mocked(drawPhotoScene).mockResolvedValue({ canvas, dispose });
  const drawImage = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext({ drawImage }));
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(callback =>
    callback(blobs.shift() ?? null)
  );
  return { canvas, dispose, drawImage };
}
const jpeg = () => new Blob([new Uint8Array([255, 216, 255, 217])], { type: 'image/jpeg' });

it('bounds both formats and downscales only the already-safe generated still when JPEG bytes exceed the cap', async () => {
  expect(photoSize('landscape', 1600)).toEqual({ width: 1600, height: 900 });
  expect(photoSize('portrait', 1600)).toEqual({ width: 1280, height: 1600 });
  const { canvas, dispose, drawImage } = setup([
    new Blob([new Uint8Array(MAX_PHOTO_BYTES + 1)], { type: 'image/jpeg' }),
    jpeg(),
  ]);
  const photo = await renderPhoto(scene(), 'landscape', new AbortController().signal);
  expect(photo.width).toBe(960);
  expect(photo.height).toBe(540);
  expect(photo.blob.type).toBe('image/jpeg');
  expect(photo.blob.size).toBeLessThanOrEqual(MAX_PHOTO_BYTES);
  expect(drawImage).toHaveBeenCalledWith(canvas, 0, 0, 960, 540);
  expect(dispose).toHaveBeenCalledOnce();
});

it.each(['null', 'taint', 'oversized', 'mime'])(
  'releases all surfaces after %s encoding failure',
  async failure => {
    const { dispose } = setup(
      failure === 'oversized'
        ? Array.from(
            { length: 2 },
            () => new Blob([new Uint8Array(MAX_PHOTO_BYTES + 1)], { type: 'image/jpeg' })
          )
        : [failure === 'mime' ? new Blob(['bad'], { type: 'image/png' }) : null]
    );
    if (failure === 'taint')
      vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(() => {
        throw new DOMException('private source', 'SecurityError');
      });
    await expect(renderPhoto(scene(), 'portrait', new AbortController().signal)).rejects.toThrow();
    expect(dispose).toHaveBeenCalledOnce();
  }
);

it('keeps encoding single-flight after a timeout until the actual native encoder callback settles', async () => {
  vi.useFakeTimers();
  setup([]);
  let complete: BlobCallback | null = null;
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(callback => {
    complete = callback;
  });
  const first = renderPhoto(scene(), 'landscape', new AbortController().signal);
  const failure = expect(first).rejects.toThrow();
  await vi.advanceTimersByTimeAsync(PHOTO_ENCODE_TIMEOUT_MS + 1);
  await failure;
  await expect(renderPhoto(scene(), 'landscape', new AbortController().signal)).rejects.toThrow(
    'busy'
  );
  const callback = complete as BlobCallback | null;
  if (!callback) throw new Error('Missing encoder callback');
  callback(jpeg());
  await Promise.resolve();
  setup([jpeg()]);
  await expect(
    renderPhoto(scene(), 'landscape', new AbortController().signal)
  ).resolves.toMatchObject({ width: 1600 });
});

it('fences an aborted owner before encoding or publication', async () => {
  const { dispose } = setup([jpeg()]);
  vi.mocked(drawPhotoScene).mockClear();
  const encode = vi.spyOn(HTMLCanvasElement.prototype, 'toBlob');
  const controller = new AbortController();
  controller.abort();
  await expect(renderPhoto(scene(), 'landscape', controller.signal)).rejects.toThrow();
  expect(drawPhotoScene).not.toHaveBeenCalled();
  expect(encode).not.toHaveBeenCalled();
  expect(dispose).not.toHaveBeenCalled();
});

it('releases the single-flight gate even when surface disposal itself fails', async () => {
  const first = setup([jpeg()]);
  first.dispose.mockImplementation(() => {
    throw new Error('dispose');
  });
  await expect(renderPhoto(scene(), 'landscape', new AbortController().signal)).rejects.toThrow(
    'dispose'
  );
  setup([jpeg()]);
  await expect(
    renderPhoto(scene(), 'landscape', new AbortController().signal)
  ).resolves.toMatchObject({ width: 1600 });
});

it('offers browser sharing only with a fresh file-capable API and distinguishes cancellation', async () => {
  const file = new File([jpeg()], 'lia-world-photo.jpg', { type: 'image/jpeg' });
  vi.stubGlobal('navigator', { canShare: () => false, share: vi.fn() });
  expect(await shareWorldPhoto(file)).toBe('unsupported');
  vi.stubGlobal('navigator', {
    canShare: () => true,
    share: vi.fn().mockRejectedValue(new DOMException('Cancelled', 'AbortError')),
  });
  expect(await shareWorldPhoto(file)).toBe('cancelled');
  vi.stubGlobal('navigator', { canShare: () => true, share: vi.fn().mockResolvedValue(undefined) });
  expect(await shareWorldPhoto(file)).toBe('offered');
});
it('treats absent or throwing capability APIs as unsupported and reports a refused share', async () => {
  const file = new File([jpeg()], 'lia-world-photo.jpg', { type: 'image/jpeg' });
  vi.stubGlobal('navigator', {});
  expect(await shareWorldPhoto(file)).toBe('unsupported');
  vi.stubGlobal('navigator', {
    share: vi.fn(),
    canShare: () => {
      throw new Error('denied');
    },
  });
  expect(await shareWorldPhoto(file)).toBe('unsupported');
  vi.stubGlobal('navigator', {
    canShare: () => true,
    share: vi.fn().mockRejectedValue(new DOMException('Denied', 'NotAllowedError')),
  });
  await expect(shareWorldPhoto(file)).rejects.toThrow('Denied');
  expect(await shareWorldPhoto(new File([], 'empty.jpg', { type: 'image/jpeg' }))).toBe(
    'unsupported'
  );
});
it('preserves browser user activation even inside an older native shell', async () => {
  Reflect.set(window, 'Capacitor', {
    isNativePlatform: () => true,
    Plugins: { LiaShell: { get: vi.fn(), shareImage: vi.fn() } },
  });
  const share = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal('navigator', { canShare: () => true, share });
  try {
    const pending = shareWorldPhoto(
      new File([jpeg()], 'lia-world-photo.jpg', { type: 'image/jpeg' }),
      () => true,
      false
    );
    expect(share).toHaveBeenCalledOnce();
    expect(await pending).toBe('offered');
  } finally {
    Reflect.deleteProperty(window, 'Capacitor');
  }
});
it('hands a preview to the positively detected native backend and fences an obsolete owner', async () => {
  const native = vi.fn().mockResolvedValue({ status: 'offered' });
  Reflect.set(window, 'Capacitor', {
    isNativePlatform: () => true,
    Plugins: {
      LiaShell: {
        get: vi.fn().mockResolvedValue({ capabilities: { shareImage: 1 } }),
        shareImage: native,
      },
    },
  });
  const browser = vi.fn();
  vi.stubGlobal('navigator', { canShare: () => true, share: browser });
  const file = new File([jpeg()], 'lia-world-photo.jpg', { type: 'image/jpeg' });
  try {
    expect(await shareWorldPhoto(file, () => true, true)).toBe('offered');
    expect(native).toHaveBeenCalledOnce();
    expect(browser).not.toHaveBeenCalled();
    await expect(shareWorldPhoto(file, () => false, true)).rejects.toThrow('owner');
    expect(native).toHaveBeenCalledOnce();
  } finally {
    Reflect.deleteProperty(window, 'Capacitor');
  }
});
it('rechecks ownership after browser capability detection before sharing any bytes', async () => {
  let current = true;
  const share = vi.fn();
  vi.stubGlobal('navigator', {
    canShare: () => {
      current = false;
      return true;
    },
    share,
  });
  await expect(
    shareWorldPhoto(
      new File([jpeg()], 'lia-world-photo.jpg', { type: 'image/jpeg' }),
      () => current
    )
  ).rejects.toThrow('owner');
  expect(share).not.toHaveBeenCalled();
});

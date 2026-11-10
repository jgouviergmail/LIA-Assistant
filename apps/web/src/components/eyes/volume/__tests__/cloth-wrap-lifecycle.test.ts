import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { volumeGraphics } from '../../__tests__/volume-graphics';
import { restChannelValues } from '../../rig/channels';
import { createClothGpu } from '../cloth-gpu';
import { bindBodyVolume, paintBodyVolume } from '../volume-binding';
import * as fringe from '../volume-fringe';
import { volumeProfile } from '../volume-geometry';
import * as masks from '../volume-mask';

/** Decode is the controlled browser boundary; all material/resource owners stay real. */
class MaterialImage {
  static instances: MaterialImage[] = [];
  src = '';
  complete = false;
  naturalWidth = 192;
  naturalHeight = 192;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor() {
    MaterialImage.instances.push(this);
  }

  load(): void {
    this.complete = true;
    this.onload?.();
  }
}

const COLD = { ...restChannelValues(), weatherCold: 0.65 };

function clothHost() {
  const gl = volumeGraphics();
  const redraw = vi.fn<() => void>();
  const cloth = createClothGpu(
    document.createElement('canvas'),
    gl,
    volumeProfile('bip', 'male').collar,
    redraw
  );
  return { gl, redraw, cloth };
}

function bodyHost() {
  const root = document.createElement('span');
  const canvas = document.createElement('canvas');
  root.dataset.rigVisible = 'true';
  canvas.width = canvas.height = 192;
  root.append(canvas);
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  // Raster readback is independent of the real body/cloth GPU ownership exercised here.
  const alpha = new Uint8Array(192 * 192);
  for (let y = 10; y < 182; y++) for (let x = 28; x < 164; x++) alpha[y * 192 + x] = 255;
  vi.spyOn(masks, 'readVolumeMask').mockReturnValue({ width: 192, height: 192, alpha });
  vi.spyOn(fringe, 'volumeFringeMask').mockReturnValue(document.createElement('canvas'));
  const gl = volumeGraphics();
  paintBodyVolume(root, COLD);
  const dispose = bindBodyVolume(canvas, root, 'bip', 'male', gl);
  MaterialImage.instances[0].load();
  return { root, canvas, gl, dispose };
}

function expectReleased(gl: ReturnType<typeof volumeGraphics>): void {
  expect(gl.deleteTexture.mock.calls.filter(([texture]) => texture !== null)).toHaveLength(
    gl.createTexture.mock.results.filter(result => result.value !== null).length
  );
  expect(gl.deleteBuffer).toHaveBeenCalledTimes(gl.createBuffer.mock.calls.length);
  expect(gl.deleteProgram).toHaveBeenCalledTimes(gl.createProgram.mock.calls.length);
}

beforeEach(() => {
  vi.stubGlobal('Image', MaterialImage);
});

afterEach(() => {
  MaterialImage.instances = [];
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('the wrapped scarf closes both material lifetimes as one visible attachment', () => {
  it.each([
    [0, 1],
    [1, 0],
  ] as const)('waits for both decoders when material %i resolves before %i', (first, second) => {
    const { root, gl, dispose } = bodyHost();
    expect(MaterialImage.instances).toHaveLength(3);
    expect(root.dataset.volumeReady).toBe('false');
    expect(root.dataset.volumeScarfReady).toBe('false');

    MaterialImage.instances[first + 1].load();
    expect(paintBodyVolume(root, COLD)).toBe(false);
    expect(root.dataset.volumeReady).toBe('false');
    expect(root.dataset.volumeScarfReady).toBe('false');
    // The retained body may paint offscreen; no partial cloth pass is visible.
    expect(gl.drawElements).toHaveBeenCalledTimes(2);

    MaterialImage.instances[second + 1].load();
    expect(paintBodyVolume(root, COLD)).toBe(true);
    expect(root.dataset.volumeReady).toBe('true');
    expect(root.dataset.volumeScarfReady).toBe('true');
    expect(gl.drawElements).toHaveBeenCalledTimes(5);
    expect(gl.texImage2D).toHaveBeenCalledTimes(4);
    dispose();
    expectReleased(gl);
  });

  it('releases an already decoded first material when the second decoder fails', () => {
    const { gl, redraw, cloth } = clothHost();
    cloth.draw(COLD);
    MaterialImage.instances[0].load();
    const staleLoad = MaterialImage.instances[1].onload;
    MaterialImage.instances[1].onerror?.();
    staleLoad?.();

    expect(cloth.draw(COLD)).toBe(false);
    expect(gl.drawElements).not.toHaveBeenCalled();
    expect(gl.texImage2D).toHaveBeenCalledOnce();
    expect(redraw).toHaveBeenCalledOnce();
    expect(MaterialImage.instances).toHaveLength(2);
    for (const image of MaterialImage.instances) {
      expect(image.onload).toBeNull();
      expect(image.onerror).toBeNull();
    }
    expectReleased(gl);
    cloth.dispose();
    expectReleased(gl);
  });

  it('rolls back the first material and the partial second allocation without retrying', () => {
    const { gl, redraw, cloth } = clothHost();
    gl.createTexture.mockReturnValueOnce({}).mockReturnValueOnce(null);
    expect(cloth.draw(COLD)).toBe(false);
    expect(MaterialImage.instances).toHaveLength(1);
    expect(MaterialImage.instances[0].onload).toBeNull();
    expect(MaterialImage.instances[0].onerror).toBeNull();
    expect(gl.createProgram).toHaveBeenCalledTimes(2);
    expectReleased(gl);

    for (let frame = 0; frame < 4; frame++) expect(cloth.draw(COLD)).toBe(false);
    expect(gl.createProgram).toHaveBeenCalledTimes(2);
    expect(gl.texImage2D).not.toHaveBeenCalled();
    expect(redraw).not.toHaveBeenCalled();
    cloth.dispose();
    expectReleased(gl);
  });

  it('closes a partial cold load on warming and reopens without uploads on later sway frames', () => {
    const { gl, redraw, cloth } = clothHost();
    expect(cloth.draw(restChannelValues())).toBe(false);
    expect(gl.createProgram).not.toHaveBeenCalled();
    cloth.draw(COLD);
    MaterialImage.instances[0].load();
    const staleLoad = MaterialImage.instances[1].onload;
    expect(cloth.draw(restChannelValues())).toBe(false);
    expectReleased(gl);
    staleLoad?.();
    expect(redraw).toHaveBeenCalledOnce();
    expect(gl.texImage2D).toHaveBeenCalledOnce();

    expect(cloth.draw(COLD)).toBe(false);
    expect(MaterialImage.instances).toHaveLength(4);
    MaterialImage.instances[3].load();
    expect(cloth.draw(COLD)).toBe(false);
    MaterialImage.instances[2].load();
    const bufferUploads = gl.bufferData.mock.calls.length;
    const textureUploads = gl.texImage2D.mock.calls.length;
    for (let frame = 0; frame < 20; frame++) {
      expect(cloth.draw({ ...COLD, scarfTrail: 0.3 * Math.sin(frame) })).toBe(true);
    }
    expect(gl.drawElements).toHaveBeenCalledTimes(40);
    expect(gl.bufferData).toHaveBeenCalledTimes(bufferUploads);
    expect(gl.texImage2D).toHaveBeenCalledTimes(textureUploads);
    expect(MaterialImage.instances).toHaveLength(4);
    cloth.dispose();
    cloth.dispose();
    expectReleased(gl);
  });

  it('restores the body with two fresh cloth decoders after losing a partial scarf load', () => {
    const { root, canvas, gl, dispose } = bodyHost();
    expect(MaterialImage.instances).toHaveLength(3);
    MaterialImage.instances[1].load();
    expect(root.dataset.volumeReady).toBe('false');
    expect(root.dataset.volumeScarfReady).toBe('false');
    const staleLoad = MaterialImage.instances[2].onload;
    const lost = new Event('webglcontextlost', { cancelable: true });
    canvas.dispatchEvent(lost);
    expect(lost.defaultPrevented).toBe(true);
    expect(root.dataset.volumeReady).toBe('false');
    expect(root.dataset.volumeScarfReady).toBe('false');
    expectReleased(gl);
    const uploadsBeforeStale = gl.texImage2D.mock.calls.length;
    const drawsBeforeStale = gl.drawElements.mock.calls.length;
    staleLoad?.();
    const traveling = { ...COLD, scarfTrail: 0.2 };
    paintBodyVolume(root, traveling);
    expect(gl.texImage2D).toHaveBeenCalledTimes(uploadsBeforeStale);
    expect(gl.drawElements).toHaveBeenCalledTimes(drawsBeforeStale);

    canvas.dispatchEvent(new Event('webglcontextrestored'));
    expect(MaterialImage.instances).toHaveLength(5);
    expect(root.dataset.volumeReady).toBe('false');
    expect(root.dataset.volumeScarfReady).toBe('false');
    MaterialImage.instances[4].load();
    expect(root.dataset.volumeReady).toBe('false');
    expect(root.dataset.volumeScarfReady).toBe('false');
    MaterialImage.instances[3].load();
    expect(root.dataset.volumeReady).toBe('true');
    expect(root.dataset.volumeScarfReady).toBe('true');
    expect(masks.readVolumeMask).toHaveBeenCalledOnce();
    expect(fringe.volumeFringeMask).toHaveBeenCalledOnce();
    const drawsAtRestore = gl.drawElements.mock.calls.length;
    expect(paintBodyVolume(root, { ...traveling, ambientSway: 0.5 })).toBe(true);
    expect(gl.drawElements).toHaveBeenCalledTimes(drawsAtRestore);
    expect(paintBodyVolume(root, COLD)).toBe(true);
    expect(gl.drawElements).toHaveBeenCalledTimes(drawsAtRestore + 3);
    dispose();
    dispose();
    expectReleased(gl);
    expect(root.dataset.volumeReady).toBe('false');
    expect(root.dataset.volumeScarfReady).toBe('false');
    const programsAfterDispose = gl.createProgram.mock.calls.length;
    canvas.dispatchEvent(new Event('webglcontextrestored'));
    expect(gl.createProgram).toHaveBeenCalledTimes(programsAfterDispose);
  });

  it('recovers the retained body after permanent cloth failure at the exact warm boundary', () => {
    const { root, gl, dispose } = bodyHost();
    MaterialImage.instances[1].load();
    MaterialImage.instances[2].onerror?.();
    expect(root.dataset.volumeReady).toBe('false');
    expect(root.dataset.volumeScarfReady).toBe('false');
    const bufferUploads = gl.bufferData.mock.calls.length;
    const textureUploads = gl.texImage2D.mock.calls.length;
    const programs = gl.createProgram.mock.calls.length;

    expect(paintBodyVolume(root, { ...COLD, weatherCold: 0.02001 })).toBe(false);
    expect(paintBodyVolume(root, { ...COLD, weatherCold: 0.02 })).toBe(true);
    expect(root.dataset.volumeReady).toBe('true');
    expect(root.dataset.volumeScarfReady).toBe('false');
    const draws = gl.drawElements.mock.calls.length;
    for (const weatherCold of [0.02, 0, -1, NaN, Infinity, -Infinity]) {
      expect(paintBodyVolume(root, { ...COLD, weatherCold, scarfTrail: 0.3 })).toBe(true);
    }
    expect(gl.drawElements).toHaveBeenCalledTimes(draws);
    expect(gl.bufferData).toHaveBeenCalledTimes(bufferUploads);
    expect(gl.texImage2D).toHaveBeenCalledTimes(textureUploads);
    expect(gl.createProgram).toHaveBeenCalledTimes(programs);
    expect(MaterialImage.instances).toHaveLength(3);
    expect(paintBodyVolume(root, COLD)).toBe(false);
    expect(root.dataset.volumeReady).toBe('false');
    dispose();
    expectReleased(gl);
  });
});

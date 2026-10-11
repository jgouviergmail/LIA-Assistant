import { afterEach, describe, expect, it, vi } from 'vitest';
import { createClothGpu } from '../cloth-gpu';
import { SMILEY_COLLAR } from '../cloth-geometry';
import { restChannelValues } from '../../rig/channels';
import { smileyClothGraphics } from '../../__tests__/smiley-cloth-graphics';

class ScarfImage {
  static instances: ScarfImage[] = [];
  src = '';
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    ScarfImage.instances.push(this);
  }
}
afterEach(() => {
  ScarfImage.instances = [];
  vi.unstubAllGlobals();
});

describe('the conditional alpha scarf material owns no independent animation resources', () => {
  it('uses the exact nonrepeating front art and opaque settled material only after decoding', () => {
    vi.stubGlobal('Image', ScarfImage);
    const gl = smileyClothGraphics(),
      redraw = vi.fn(),
      cloth = createClothGpu(document.createElement('canvas'), gl, SMILEY_COLLAR, redraw);
    const cold = { ...restChannelValues(), weatherCold: 0.65 };
    expect(cloth.draw(restChannelValues())).toBe(false);
    expect(gl.createTexture).not.toHaveBeenCalled();
    expect(cloth.draw(cold)).toBe(false);
    expect(ScarfImage.instances[0].src).toBe('/avatars/scarf/v1/front.webp');
    ScarfImage.instances[0].onload?.();
    expect(redraw).toHaveBeenCalledTimes(1);
    expect(cloth.draw(cold)).toBe(true);
    expect(gl.depthFunc.mock.calls).toEqual([[gl.ALWAYS], [gl.LEQUAL]]);
    expect(gl.depthMask.mock.calls).toEqual([[false], [true]]);
    expect(gl.texParameteri).toHaveBeenCalledWith(
      gl.TEXTURE_2D,
      gl.TEXTURE_WRAP_S,
      gl.CLAMP_TO_EDGE
    );
    expect(gl.texParameteri).toHaveBeenCalledWith(
      gl.TEXTURE_2D,
      gl.TEXTURE_WRAP_T,
      gl.CLAMP_TO_EDGE
    );
    expect(gl.uniform1f).toHaveBeenCalledWith(expect.anything(), 1);
    cloth.dispose();
  });
  it('restores body depth state even if the native front pass cannot complete', () => {
    vi.stubGlobal('Image', ScarfImage);
    const gl = smileyClothGraphics(),
      cloth = createClothGpu(document.createElement('canvas'), gl, SMILEY_COLLAR, vi.fn()),
      cold = { ...restChannelValues(), weatherCold: 0.65 };
    cloth.draw(cold);
    ScarfImage.instances[0].onload?.();
    gl.drawElements.mockImplementationOnce(() => {
      throw new Error('Context draw rejected');
    });
    expect(() => cloth.draw(cold)).toThrow('Context draw rejected');
    expect(gl.depthFunc.mock.calls.at(-1)).toEqual([gl.LEQUAL]);
    expect(gl.depthMask.mock.calls.at(-1)).toEqual([true]);
    cloth.dispose();
  });
  it('releases texture and mesh when warming, reopens lazily, and ignores a stale decoder callback', () => {
    vi.stubGlobal('Image', ScarfImage);
    const gl = smileyClothGraphics(),
      redraw = vi.fn(),
      cloth = createClothGpu(document.createElement('canvas'), gl, SMILEY_COLLAR, redraw);
    const cold = { ...restChannelValues(), weatherCold: 0.65 };
    cloth.draw(cold);
    const previous = ScarfImage.instances[0],
      staleLoad = previous.onload;
    expect(cloth.draw(restChannelValues())).toBe(false);
    expect(gl.deleteTexture).toHaveBeenCalledTimes(1);
    expect(previous.onload).toBeNull();
    expect(previous.onerror).toBeNull();
    expect(cloth.draw(cold)).toBe(false);
    expect(ScarfImage.instances).toHaveLength(2);
    staleLoad?.();
    expect(gl.texImage2D).not.toHaveBeenCalled();
    expect(redraw).not.toHaveBeenCalled();
    ScarfImage.instances[1].onload?.();
    expect(cloth.draw(cold)).toBe(true);
    cloth.dispose();
    cloth.dispose();
    expect(gl.deleteTexture).toHaveBeenCalledTimes(gl.createTexture.mock.calls.length);
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(gl.createBuffer.mock.calls.length);
    expect(gl.deleteProgram).toHaveBeenCalledTimes(gl.createProgram.mock.calls.length);
  });
  it('retains the DOM fallback after a failed material without retries or a new frame clock', () => {
    vi.stubGlobal('Image', ScarfImage);
    const gl = smileyClothGraphics(),
      redraw = vi.fn(),
      raf = vi.spyOn(window, 'requestAnimationFrame'),
      cloth = createClothGpu(document.createElement('canvas'), gl, SMILEY_COLLAR, redraw);
    const cold = { ...restChannelValues(), weatherCold: 0.65 };
    cloth.draw(cold);
    ScarfImage.instances[0].onerror?.();
    for (let i = 0; i < 4; i++) expect(cloth.draw(cold)).toBe(false);
    expect(ScarfImage.instances).toHaveLength(1);
    expect(gl.deleteTexture).toHaveBeenCalledTimes(1);
    expect(redraw).not.toHaveBeenCalled();
    expect(raf).not.toHaveBeenCalled();
    cloth.dispose();
    raf.mockRestore();
  });
});

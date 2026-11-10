import { afterEach, describe, expect, it, vi } from 'vitest';
import { createClothGpu } from '../cloth-gpu';
import { volumeProfile } from '../volume-geometry';
const COLLAR = volumeProfile('monitor', 'male').collar;
import { restChannelValues } from '../../rig/channels';
import { volumeGraphics } from '../../__tests__/volume-graphics';
import { mapScarfUv, SCARF_ART } from '../scarf-fit';
import { scarfKnotFacets } from '../scarf-wrap';

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
  it('waits for both wrapped materials, preserves occlusion and moves only below the knot seam', () => {
    vi.stubGlobal('Image', ScarfImage);
    const gl = volumeGraphics();
    const collar = volumeProfile('bip', 'female').collar;
    const cloth = createClothGpu(document.createElement('canvas'), gl, collar, vi.fn());
    const cold = { ...restChannelValues(), weatherCold: 0.65, scarfTrail: 0.2 };
    expect(cloth.draw(cold)).toBe(false);
    expect(ScarfImage.instances).toHaveLength(2);
    ScarfImage.instances[1].onload?.();
    expect(cloth.draw(cold)).toBe(false);
    expect(gl.drawElements).not.toHaveBeenCalled();
    ScarfImage.instances[0].onload?.();
    expect(cloth.draw(cold)).toBe(true);
    expect(gl.depthFunc.mock.calls).toEqual([[gl.LEQUAL], [gl.LEQUAL]]);
    expect(gl.depthMask.mock.calls).toEqual([[true], [false], [true]]);
    const drapes = gl.getUniformLocation.mock.calls.flatMap(([, name], i) =>
      name === 'u_drape' ? [gl.getUniformLocation.mock.results[i].value] : []
    );
    expect(gl.uniform2fv).toHaveBeenCalledWith(drapes[0], new Float32Array([0, 0]));
    expect(gl.uniform2fv).toHaveBeenCalledWith(
      drapes[1],
      new Float32Array([0.2, scarfKnotFacets(collar)[1].origin.y])
    );
    const allocations = gl.bufferData.mock.calls.length;
    cloth.draw({ ...cold, scarfTrail: -0.2 });
    expect(gl.bufferData).toHaveBeenCalledTimes(allocations);
    cloth.dispose();
    expect(gl.deleteTexture).toHaveBeenCalledTimes(2);
  });

  it('a failed second wrapped texture releases both owners and ignores their stale callbacks', () => {
    vi.stubGlobal('Image', ScarfImage);
    const gl = volumeGraphics(),
      redraw = vi.fn();
    const cloth = createClothGpu(
      document.createElement('canvas'),
      gl,
      volumeProfile('nimbo', 'male').collar,
      redraw
    );
    const cold = { ...restChannelValues(), weatherCold: 0.65 };
    cloth.draw(cold);
    const stale = ScarfImage.instances[0].onload;
    ScarfImage.instances[1].onerror?.();
    stale?.();
    expect(gl.texImage2D).not.toHaveBeenCalled();
    expect(gl.deleteTexture).toHaveBeenCalledTimes(2);
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(gl.createBuffer.mock.calls.length);
    expect(cloth.draw(cold)).toBe(false);
    expect(ScarfImage.instances).toHaveLength(2);
    expect(redraw).not.toHaveBeenCalled();
    cloth.dispose();
  });

  it('uses the exact nonrepeating front art and opaque settled material only after decoding', () => {
    vi.stubGlobal('Image', ScarfImage);
    const gl = volumeGraphics(),
      redraw = vi.fn(),
      cloth = createClothGpu(document.createElement('canvas'), gl, COLLAR, redraw);
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
    const gl = volumeGraphics(),
      cloth = createClothGpu(document.createElement('canvas'), gl, COLLAR, vi.fn()),
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
  it('updates the free end without preparing geometry or decoding the art again', () => {
    vi.stubGlobal('Image', ScarfImage);
    const gl = volumeGraphics(),
      cloth = createClothGpu(document.createElement('canvas'), gl, COLLAR, vi.fn()),
      cold = { ...restChannelValues(), weatherCold: 0.65, scarfTrail: 0.2 };
    cloth.draw(cold);
    ScarfImage.instances[0].onload?.();
    gl.uniform2fv.mockClear();
    cloth.draw(cold);
    const drapeLocation =
      gl.getUniformLocation.mock.results[
        gl.getUniformLocation.mock.calls.findIndex(([, name]) => name === 'u_drape')
      ].value;
    const seamY = mapScarfUv(COLLAR, 0, SCARF_ART.tailStart).y;
    expect(gl.uniform2fv).toHaveBeenCalledWith(drapeLocation, new Float32Array([0.2, seamY]));
    const preparations = gl.bufferData.mock.calls.length;
    gl.uniform2fv.mockClear();
    cloth.draw({ ...cold, scarfTrail: -0.2 });
    expect(gl.uniform2fv).toHaveBeenCalledWith(drapeLocation, new Float32Array([-0.2, seamY]));
    expect(gl.bufferData).toHaveBeenCalledTimes(preparations);
    expect(ScarfImage.instances).toHaveLength(1);
    cloth.dispose();
  });
  it('releases texture and mesh when warming, reopens lazily, and ignores a stale decoder callback', () => {
    vi.stubGlobal('Image', ScarfImage);
    const gl = volumeGraphics(),
      redraw = vi.fn(),
      cloth = createClothGpu(document.createElement('canvas'), gl, COLLAR, redraw);
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
    const gl = volumeGraphics(),
      redraw = vi.fn(),
      raf = vi.spyOn(window, 'requestAnimationFrame'),
      cloth = createClothGpu(document.createElement('canvas'), gl, COLLAR, redraw);
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

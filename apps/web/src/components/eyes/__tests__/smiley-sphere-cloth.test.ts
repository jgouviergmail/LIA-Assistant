import { afterEach, describe, expect, it, vi } from 'vitest';
import { createSphereGpu } from '../smiley/sphere-gpu';
import { restChannelValues } from '../rig/channels';
import { smileyClothGraphics } from './smiley-cloth-graphics';
import { clothMesh, SMILEY_COLLAR } from '../volume/cloth-geometry';

class ClothImage {
  static instances: ClothImage[] = [];
  src = '';
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    ClothImage.instances.push(this);
  }
}

afterEach(() => {
  ClothImage.instances = [];
  vi.unstubAllGlobals();
});

function canvas() {
  const node = document.createElement('canvas');
  node.width = node.height = 192;
  return node;
}

describe('The native sphere and sculpted front scarf share one bounded GL scene', () => {
  it('keeps the frontal scarf UV registration on the true sphere and its knot in front', () => {
    const mesh = clothMesh(SMILEY_COLLAR);
    const width = SMILEY_COLLAR.radiusX * 2.2;
    expect(mesh.vertices.length / 8).toBeLessThanOrEqual(1024);
    for (let i = 0; i < mesh.vertices.length; i += 8) {
      const [x, y, z, nx, ny, nz, u, v] = mesh.vertices.slice(i, i + 8);
      expect(u).toBeGreaterThanOrEqual(0);
      expect(u).toBeLessThanOrEqual(1);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(1);
      expect(x).toBeCloseTo((u - 0.5) * width, 5);
      expect(y).toBeCloseTo(SMILEY_COLLAR.centerY + (v - 0.54) * width, 5);
      expect(z).toBeGreaterThanOrEqual(Math.sqrt(Math.max(0, 1.274 ** 2 - x * x - y * y)) + 0.0249);
      expect(Math.hypot(nx, ny, nz)).toBeCloseTo(1, 5);
    }
  });
  it('loads no mesh/material until cold and visible, then releases cloth on warming and hiding', () => {
    vi.stubGlobal('Image', ClothImage);
    const gl = smileyClothGraphics();
    const redraw = vi.fn();
    const gpu = createSphereGpu(canvas(), gl, 'female', redraw)!;
    const rest = restChannelValues(),
      cold = { ...rest, weatherCold: 0.65 };
    expect(gpu.draw(rest)).toBe(false);
    expect(gl.createTexture).not.toHaveBeenCalled();
    expect(gpu.draw(cold, false)).toBe(false);
    expect(ClothImage.instances).toHaveLength(0);
    expect(gpu.draw(cold)).toBe(false);
    expect(ClothImage.instances).toHaveLength(1);
    expect(ClothImage.instances[0].src).toBe('/avatars/scarf/v1/front.webp');
    ClothImage.instances[0].onload?.();
    expect(redraw).toHaveBeenCalledTimes(1);
    expect(gpu.draw(cold)).toBe(true);
    expect(gl.drawElements).toHaveBeenCalledTimes(1);
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
    expect(gpu.draw(rest)).toBe(false);
    expect(gl.deleteTexture).toHaveBeenCalledTimes(1);
    expect(gpu.draw(cold)).toBe(false);
    const pending = ClothImage.instances[1];
    expect(gpu.draw(cold, false)).toBe(false);
    expect(gl.deleteTexture).toHaveBeenCalledTimes(2);
    expect(pending.onload).toBeNull();
    gpu.dispose();
    gpu.dispose();
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(gl.createBuffer.mock.calls.length);
    expect(gl.deleteProgram).toHaveBeenCalledTimes(gl.createProgram.mock.calls.length);
  });

  it('preserves the original body and DOM collar fallback without true fragment depth', () => {
    vi.stubGlobal('Image', ClothImage);
    const gl = smileyClothGraphics(false),
      gpu = createSphereGpu(canvas(), gl)!;
    const rest = restChannelValues();
    gpu.draw(rest);
    expect(gpu.draw({ ...rest, weatherCold: 0.65 })).toBe(false);
    expect(gl.createTexture).not.toHaveBeenCalled();
    expect(ClothImage.instances).toHaveLength(0);
    expect(gl.drawArrays).toHaveBeenCalledTimes(1);
    gpu.dispose();
  });

  it('restores the body vertex layout after cloth painting and clears a changed native sway', () => {
    vi.stubGlobal('Image', ClothImage);
    const gl = smileyClothGraphics(),
      gpu = createSphereGpu(canvas(), gl)!;
    const cold = { ...restChannelValues(), weatherCold: 0.65 };
    gpu.draw(cold);
    expect(ClothImage.instances).toHaveLength(1);
    ClothImage.instances[0].onload?.();
    gpu.draw(cold);
    let bodyRestored = false;
    gl.drawArrays.mockImplementation(() => {
      const pointer = gl.vertexAttribPointer.mock.calls.at(-1)!;
      bodyRestored = pointer[1] === 2 && pointer[4] === 0;
    });
    const count = gl.clear.mock.calls.length;
    gpu.draw({ ...cold, ambientSway: 0.1 });
    expect(bodyRestored).toBe(true);
    expect(gl.clear).toHaveBeenCalledTimes(count + 1);
    gpu.dispose();
  });
});

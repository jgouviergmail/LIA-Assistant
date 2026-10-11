import { describe, expect, it, vi } from 'vitest';
import { createSphereGpu } from '../smiley/sphere-gpu';
import { sphereGraphics } from './sphere-graphics';
import { restChannelValues } from '../rig/channels';

function depthGraphics(supported: boolean) {
  return {
    ...sphereGraphics(),
    DEPTH_TEST: 2929 as const,
    DEPTH_BUFFER_BIT: 256 as const,
    COLOR_BUFFER_BIT: 16384 as const,
    LEQUAL: 515 as const,
    getExtension: vi.fn(() => (supported ? {} : null)),
    getContextAttributes: vi.fn(() => ({ depth: true })),
    enable: vi.fn(),
    depthFunc: vi.fn(),
    clearDepth: vi.fn(),
    clearColor: vi.fn(),
    clear: vi.fn(),
  };
}

describe('The Smiley occludes cloth with its actual spherical surface depth', () => {
  it('keeps the original sphere when fragment depth is unavailable', () => {
    const gl = depthGraphics(false);
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 104;
    const gpu = createSphereGpu(canvas, gl)!;
    gpu.draw(restChannelValues());
    expect(gl.getExtension).toHaveBeenCalledWith('EXT_frag_depth');
    expect(gl.enable).not.toHaveBeenCalled();
    expect(gl.drawArrays).toHaveBeenCalledWith(gl.TRIANGLES, 0, 6);
    expect(
      gl.shaderSource.mock.calls.some(([, source]) => source.includes('gl_FragDepthEXT'))
    ).toBe(false);
    gpu.dispose();
  });

  it('clears the real depth buffer on head changes and retains the mouth-only draw cache', () => {
    const gl = depthGraphics(true);
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 192;
    const gpu = createSphereGpu(canvas, gl)!;
    const values = restChannelValues();
    gpu.draw(values);
    expect(gl.enable).toHaveBeenCalledWith(gl.DEPTH_TEST);
    expect(gl.depthFunc).toHaveBeenCalledWith(gl.LEQUAL);
    expect(gl.clearDepth).toHaveBeenCalledWith(1);
    expect(gl.clear).toHaveBeenCalledWith(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gpu.draw({ ...values, mouthOpen: 0.5 });
    expect(gl.clear).toHaveBeenCalledTimes(1);
    gpu.draw({ ...values, headYaw: 0.8 });
    expect(gl.clear).toHaveBeenCalledTimes(2);
    gpu.dispose();
  });

  it('does not pretend to have surface depth on a context without a depth buffer', () => {
    const gl = depthGraphics(true);
    gl.getContextAttributes.mockReturnValue({ depth: false });
    const gpu = createSphereGpu(document.createElement('canvas'), gl)!;
    gpu.draw(restChannelValues());
    expect(gl.enable).not.toHaveBeenCalled();
    expect(
      gl.shaderSource.mock.calls.some(([, source]) => source.includes('gl_FragDepthEXT'))
    ).toBe(false);
    gpu.dispose();
  });
});

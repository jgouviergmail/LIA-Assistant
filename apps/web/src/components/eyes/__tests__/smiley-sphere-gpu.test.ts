import { describe, expect, it } from 'vitest';
import { createSphereGpu } from '../smiley/sphere-gpu';
import { sphereGraphics } from './sphere-graphics';
import { restChannelValues } from '../rig/channels';

function canvas() {
  const element = document.createElement('canvas');
  element.width = element.height = 104;
  return element;
}

describe('Native single-pass spherical renderer', () => {
  it('gates the local-normal cheek material by gender with the male base unchanged', () => {
    for (const variant of ['male', 'female'] as const) {
      const gl = sphereGraphics();
      const locations = new Map<WebGLUniformLocation, string>();
      gl.getUniformLocation.mockImplementation((_program, name) => {
        const location = {};
        locations.set(location, name);
        return location;
      });
      const gpu = createSphereGpu(canvas(), gl, variant)!;
      expect(
        gl.uniform1f.mock.calls.some(
          ([location, value]) =>
            locations.get(location) === 'u_female' && value === Number(variant === 'female')
        )
      ).toBe(true);
      gpu.dispose();
    }
  });
  it('draws two triangles once, caches the body and does not redraw it for mouth-only motion', () => {
    const gl = sphereGraphics();
    const gpu = createSphereGpu(canvas(), gl)!;
    const values = restChannelValues();
    gpu.draw(values);
    expect(gl.drawArrays).toHaveBeenCalledWith(gl.TRIANGLES, 0, 6);
    expect(gl.viewport).toHaveBeenCalledWith(0, 0, 104, 104);
    gpu.draw(values);
    gpu.draw({ ...values, mouthOpen: 0.6 });
    expect(gl.drawArrays).toHaveBeenCalledTimes(1);
    gpu.draw({ ...values, headYaw: 0.7, lightWarm: 0.3 });
    expect(gl.drawArrays).toHaveBeenCalledTimes(2);
    gpu.reset();
    gpu.draw(values);
    expect(gl.drawArrays).toHaveBeenCalledTimes(3);
    gpu.dispose();
    gpu.dispose();
    gpu.draw(values);
    expect(gl.drawArrays).toHaveBeenCalledTimes(3);
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(1);
    expect(gl.deleteProgram).toHaveBeenCalledTimes(1);
    expect(gl.deleteShader).toHaveBeenCalledTimes(2);
  });

  it('releases partially compiled resources when linking fails without a retry', () => {
    const gl = sphereGraphics();
    gl.getProgramParameter.mockReturnValue(false);
    expect(createSphereGpu(canvas(), gl)).toBeNull();
    expect(gl.deleteShader).toHaveBeenCalledTimes(2);
    expect(gl.deleteProgram).toHaveBeenCalledTimes(1);
    expect(gl.createBuffer).not.toHaveBeenCalled();
  });

  it('releases the program when the bounded vertex buffer cannot be allocated', () => {
    const gl = sphereGraphics();
    gl.createBuffer.mockReturnValue(null);
    expect(createSphereGpu(canvas(), gl)).toBeNull();
    expect(gl.deleteProgram).toHaveBeenCalledTimes(1);
    expect(gl.drawArrays).not.toHaveBeenCalled();
  });
});

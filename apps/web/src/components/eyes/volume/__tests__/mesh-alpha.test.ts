import { describe, expect, it } from 'vitest';
import { createMeshGpu } from '../mesh-gpu';
import { volumeGraphics } from '../../__tests__/volume-graphics';

describe('source-alpha material isolation', () => {
  it('keeps the default material identity transfer for cloth and unrelated callers', () => {
    const gl = volumeGraphics();
    const uniforms = new Map<string, WebGLUniformLocation>();
    gl.getUniformLocation.mockImplementation((_program, name) => {
      const location = {};
      uniforms.set(name, location);
      return location;
    });
    const gpu = createMeshGpu(document.createElement('canvas'), gl, {
      vertices: new Float32Array(),
      indices: new Uint16Array(),
    })!;
    gpu.upload(document.createElement('canvas'));
    expect(gpu.draw({ yaw: 0, pitch: 0 })).toBe(true);
    expect(gl.uniform2fv).toHaveBeenCalledWith(
      uniforms.get('u_alpha_transfer'),
      new Float32Array([1, 0])
    );
    expect(gl.uniform1f).toHaveBeenCalledWith(uniforms.get('u_alpha_cutoff'), 0.004);
    const fragment = gl.shaderSource.mock.calls[1][1];
    expect(fragment).toContain('tex.a=clamp(tex.a*u_alpha_transfer.x+u_alpha_transfer.y,0.,1.)');
    expect(fragment).not.toMatch(/tex\.rgb\s*=/);
    expect(fragment).toContain('min(tex.a,texture2D(u_fringe,v_uv).a)');
    gpu.dispose();
  });
});

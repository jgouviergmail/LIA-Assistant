import { afterEach, describe, expect, it, vi } from 'vitest';
import { volumeFringeMask, withSoftFringe } from '../volume-fringe';
import { bodySurfaceProfile } from '../volume-distance';
import { visibleVolumeMesh, volumeProfile, rotateVolumePoint } from '../volume-geometry';
import { createMeshGpu } from '../mesh-gpu';
import { createClothGpu } from '../cloth-gpu';
import { restChannelValues } from '../../rig/channels';
import { smileyClothGraphics } from '../../__tests__/smiley-cloth-graphics';

const canvasContext = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, 'getContext')!;
afterEach(() => {
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', canvasContext);
  vi.unstubAllGlobals();
});
describe('soft source alpha never becomes an opaque physical rear or side', () => {
  it('preserves opaque source pixels missing from a sampled edge using the same depth-tested material film', () => {
    const profile = volumeProfile('oscar', 'female'),
      physical = { vertices: new Float32Array(), indices: new Uint16Array() },
      mesh = withSoftFringe(physical, profile),
      gl = smileyClothGraphics();
    const gpu = createMeshGpu(document.createElement('canvas'), gl, mesh);
    const fragment = gl.shaderSource.mock.calls
      .map(([, source]) => source)
      .find(source => source.includes('texture2D'))!;
    // Coverage may have any original alpha: coarse hull coverage must not erase an opaque hair pixel.
    expect(fragment).not.toMatch(/tex\.a\s*>=\s*180/);
    expect(fragment).toContain('float alpha=min(tex.a,texture2D(u_fringe,v_uv).a)');
    expect(fragment).toContain('gl_FragColor=vec4(tex.rgb*alpha,alpha)');
    expect(mesh.vertices.length / 8).toBe(4);
    expect(mesh.indices.length).toBe(6);
    gpu?.dispose();
  });
  it('joins front and rear normals at a radial contour without interpolating opposite rear signs', () => {
    const alpha = new Uint8Array(192 * 192);
    for (let y = 30; y < 160; y++) for (let x = 30; x < 160; x++) alpha[y * 192 + x] = 255;
    const profile = bodySurfaceProfile(volumeProfile('oscar', 'female'), {
        width: 192,
        height: 192,
        alpha,
      }),
      mesh = visibleVolumeMesh(profile, { width: 192, height: 192, alpha });
    let mixedRear = false;
    let rearTriangles = 0;
    for (let i = 0; i < mesh.indices.length; i += 3) {
      const indices = [...mesh.indices.slice(i, i + 3)];
      if (!indices.some(index => mesh.vertices[index * 8 + 2] < 0)) continue;
      rearTriangles++;
      const normals = indices.map(index => mesh.vertices[index * 8 + 5]);
      mixedRear ||= Math.min(...normals) < -0.0000001 && Math.max(...normals) > 0.0000001;
    }
    expect(rearTriangles).toBeGreaterThan(100);
    expect(mixedRear).toBe(false);
    const contour = [...new Set(mesh.indices)].filter(index => mesh.vertices[index * 8 + 2] === 0);
    expect(contour.length).toBeGreaterThan(40);
    expect(contour.every(index => Math.abs(mesh.vertices[index * 8 + 5]) < 0.0000001)).toBe(true);
    const gl = smileyClothGraphics(),
      gpu = createMeshGpu(document.createElement('canvas'), gl, mesh);
    const sources = gl.shaderSource.mock.calls.map(([, source]) => source),
      vertex = sources.find(source => source.includes('attribute'))!,
      fragment = sources.find(source => source.includes('texture2D'))!;
    expect(vertex).toMatch(/abs\(a_normal\.z\)/);
    expect(fragment).not.toMatch(/abs\(v_original\.z\)/);
    expect(fragment).toContain('float rim=u_case*v_material.y');
    gpu?.upload(document.createElement('canvas'));
    expect(gpu?.draw({ yaw: 0.2, pitch: 0 })).toBe(true);
    const caseIndex = gl.getUniformLocation.mock.calls.findIndex(([, name]) => name === 'u_case');
    expect(gl.uniform1f).toHaveBeenCalledWith(
      gl.getUniformLocation.mock.results[caseIndex].value,
      0
    );
    gpu?.dispose();
  });
  it('preserves the complete closed hull and adds only two planar source-fringe triangles', () => {
    const alpha = new Uint8Array(192 * 192);
    for (let y = 30; y < 160; y++) for (let x = 30; x < 160; x++) alpha[y * 192 + x] = 255;
    const mask = { width: 192, height: 192, alpha },
      profile = bodySurfaceProfile(volumeProfile('spirit', 'female'), mask);
    const physical = visibleVolumeMesh(profile, mask),
      combined = withSoftFringe(physical, profile);
    expect(combined.indices.slice(0, physical.indices.length)).toEqual(physical.indices);
    expect(combined.vertices.slice(0, physical.vertices.length)).toEqual(physical.vertices);
    expect(combined.vertices.length - physical.vertices.length).toBe(32);
    expect(combined.indices.length - physical.indices.length).toBe(6);
    for (let i = physical.vertices.length; i < combined.vertices.length; i += 8) {
      expect(combined.vertices[i + 2]).toBe(0);
      expect(combined.vertices[i + 5]).toBe(2);
      expect(combined.vertices[i]).toBeCloseTo(
        (combined.vertices[i + 6] - 0.5) * 2.6 * profile.scale,
        6
      );
      expect(combined.vertices[i + 1]).toBeCloseTo(
        (combined.vertices[i + 7] - 0.5) * 2.6 * profile.scale,
        6
      );
      const p = { x: combined.vertices[i], y: combined.vertices[i + 1], z: 0 };
      expect(rotateVolumePoint(p, { yaw: 0.36, pitch: 0.1 })).toEqual(
        rotateVolumePoint({ ...p, z: -0 }, { yaw: 0.36, pitch: 0.1 })
      );
    }
  });
});

function materialDriver() {
  const gl = smileyClothGraphics();
  const uniforms = new Map<string, WebGLUniformLocation>();
  gl.getUniformLocation.mockImplementation((_program, name) => {
    const location = {};
    uniforms.set(name, location);
    return location;
  });
  const profile = volumeProfile('spirit', 'female');
  const mesh = withSoftFringe(
    { vertices: new Float32Array(), indices: new Uint16Array() },
    profile
  );
  const image = document.createElement('canvas');
  const mask = document.createElement('canvas');
  mask.width = mask.height = image.width = image.height = 192;
  return { gl, uniforms, mesh, image, mask };
}

describe('the optional fringe mask shares the body material resource lifetime', () => {
  it('keeps the decoded native scarf on its authored alpha material rather than an opaque casing', () => {
    const image = document.createElement('img');
    vi.stubGlobal(
      'Image',
      class {
        constructor() {
          return image;
        }
      }
    );
    const { gl, uniforms } = materialDriver();
    const profile = volumeProfile('spirit', 'female');
    const cloth = createClothGpu(document.createElement('canvas'), gl, profile.collar, vi.fn());
    const cold = { ...restChannelValues(), weatherCold: 0.65 };
    expect(cloth.draw(cold)).toBe(false);
    image.onload?.(new Event('load'));
    expect(cloth.draw(cold)).toBe(true);
    expect(gl.uniform1f).toHaveBeenCalledWith(uniforms.get('u_case'), 0);
    cloth.dispose();
  });

  it('retains the explicit opaque casing flag for a monitor material', () => {
    const { gl, uniforms, mesh, image } = materialDriver();
    const gpu = createMeshGpu(document.createElement('canvas'), gl, mesh, false, 1.3, true)!;
    gpu.upload(image);
    expect(gpu.draw({ yaw: -0.3, pitch: 0.1 })).toBe(true);
    expect(gl.uniform1f).toHaveBeenCalledWith(uniforms.get('u_case'), 1);
    gpu.dispose();
  });

  it('keeps an unmasked material on one texture without allocating a fringe sampler', () => {
    const { gl, uniforms, mesh, image } = materialDriver();
    const gpu = createMeshGpu(document.createElement('canvas'), gl, mesh)!;
    gpu.upload(image);
    expect(gl.createTexture).toHaveBeenCalledTimes(1);
    expect(gl.texImage2D).toHaveBeenCalledTimes(1);
    expect(gpu.draw({ yaw: 0, pitch: 0 })).toBe(true);
    expect(gl.uniform1i).toHaveBeenCalledWith(uniforms.get('u_texture'), 0);
    expect(gl.uniform1i).toHaveBeenCalledWith(uniforms.get('u_fringe'), 0);
    expect(gl.activeTexture).not.toHaveBeenCalledWith(gl.TEXTURE0 + 1);
    gpu.dispose();
    gpu.dispose();
    expect(gl.deleteTexture).toHaveBeenCalledTimes(1);
  });

  it('uploads the mask on unit one and rebinds both samplers after another material used them', () => {
    const { gl, uniforms, mesh, image, mask } = materialDriver();
    const gpu = createMeshGpu(document.createElement('canvas'), gl, mesh)!;
    gpu.upload(image, mask);
    expect(gl.createTexture).toHaveBeenCalledTimes(2);
    const texture = gl.createTexture.mock.results[0].value;
    const fringe = gl.createTexture.mock.results[1].value;
    expect(gl.texImage2D.mock.calls.map(call => call.at(-1))).toEqual([mask, image]);
    // The scarf and body share a context. Every draw must restore its own
    // bindings, rather than rely on whatever texture the previous port left.
    gl.activeTexture(gl.TEXTURE0 + 1);
    gl.bindTexture(gl.TEXTURE_2D, {});
    gl.activeTexture.mockClear();
    gl.bindTexture.mockClear();
    expect(gpu.draw({ yaw: -0.3, pitch: 0.1 })).toBe(true);
    expect(gl.activeTexture.mock.calls).toEqual([[gl.TEXTURE0], [gl.TEXTURE0 + 1]]);
    expect(gl.bindTexture.mock.calls).toEqual([
      [gl.TEXTURE_2D, texture],
      [gl.TEXTURE_2D, fringe],
    ]);
    expect(gl.uniform1i).toHaveBeenCalledWith(uniforms.get('u_texture'), 0);
    expect(gl.uniform1i).toHaveBeenCalledWith(uniforms.get('u_fringe'), 1);
    gpu.dispose();
  });

  it('reuses its optional texture and releases every allocation exactly once', () => {
    const { gl, mesh, image, mask } = materialDriver();
    const gpu = createMeshGpu(document.createElement('canvas'), gl, mesh)!;
    gpu.upload(image, mask);
    gpu.upload(image, mask);
    gpu.draw({ yaw: 0.3, pitch: 0 });
    gpu.draw({ yaw: -0.3, pitch: 0 });
    expect(gl.createTexture).toHaveBeenCalledTimes(2);
    const allocated = gl.createTexture.mock.results.map(result => result.value);
    gpu.dispose();
    gpu.dispose();
    expect(gl.deleteTexture).toHaveBeenCalledTimes(2);
    for (const texture of allocated)
      expect(gl.deleteTexture.mock.calls.filter(([deleted]) => deleted === texture)).toHaveLength(
        1
      );
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(2);
    expect(gl.deleteProgram).toHaveBeenCalledTimes(1);
    const uploads = gl.texImage2D.mock.calls.length;
    const draws = gl.drawElements.mock.calls.length;
    gpu.upload(image, mask);
    expect(gpu.draw({ yaw: 0, pitch: 0 })).toBe(false);
    expect(gl.texImage2D).toHaveBeenCalledTimes(uploads);
    expect(gl.drawElements).toHaveBeenCalledTimes(draws);
  });

  it('disables a previous mask on an unmasked upload without reallocating its cached texture', () => {
    const { gl, uniforms, mesh, image, mask } = materialDriver();
    const gpu = createMeshGpu(document.createElement('canvas'), gl, mesh)!;
    gpu.upload(image, mask);
    gpu.draw({ yaw: 0.3, pitch: 0 });
    expect(gl.uniform1i).toHaveBeenLastCalledWith(uniforms.get('u_fringe'), 1);
    gpu.upload(image);
    gl.uniform1i.mockClear();
    gl.activeTexture.mockClear();
    gl.bindTexture.mockClear();
    expect(gpu.draw({ yaw: -0.3, pitch: 0 })).toBe(true);
    expect(gl.uniform1i).toHaveBeenCalledWith(uniforms.get('u_fringe'), 0);
    expect(gl.uniform1i).not.toHaveBeenCalledWith(uniforms.get('u_fringe'), 1);
    expect(gl.activeTexture.mock.calls).toEqual([[gl.TEXTURE0]]);
    expect(gl.bindTexture.mock.calls).toEqual([
      [gl.TEXTURE_2D, gl.createTexture.mock.results[0].value],
    ]);
    expect(gl.createTexture).toHaveBeenCalledTimes(2);
    gpu.dispose();
    expect(gl.deleteTexture).toHaveBeenCalledTimes(2);
  });

  it('keeps the fallback when the optional allocation fails, even after an earlier unmasked draw', () => {
    const { gl, mesh, image, mask } = materialDriver();
    const texture = {};
    gl.createTexture.mockReturnValueOnce(texture).mockReturnValueOnce(null);
    const gpu = createMeshGpu(document.createElement('canvas'), gl, mesh)!;
    gpu.upload(image);
    expect(gpu.draw({ yaw: 0, pitch: 0 })).toBe(true);
    const draws = gl.drawElements.mock.calls.length;
    const uploads = gl.texImage2D.mock.calls.length;
    gpu.upload(image, mask);
    expect(gl.createTexture).toHaveBeenCalledTimes(2);
    expect(gpu.draw({ yaw: 0.3, pitch: 0 })).toBe(false);
    expect(gl.drawElements).toHaveBeenCalledTimes(draws);
    expect(gl.texImage2D).toHaveBeenCalledTimes(uploads);
    gpu.dispose();
    gpu.dispose();
    expect(gl.deleteTexture.mock.calls).toEqual([[texture]]);
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(2);
    expect(gl.deleteProgram).toHaveBeenCalledTimes(1);
  });

  it.each(['program', 'vertex-shader', 'fragment-shader'] as const)(
    'releases the initial objects when context loss rejects the %s allocation',
    missing => {
      const { gl, mesh } = materialDriver();
      if (missing === 'program') gl.createProgram.mockReturnValueOnce(null);
      if (missing === 'vertex-shader') gl.createShader.mockReturnValueOnce(null);
      if (missing === 'fragment-shader')
        gl.createShader.mockReturnValueOnce({}).mockReturnValueOnce(null);
      expect(createMeshGpu(document.createElement('canvas'), gl, mesh)).toBeNull();
      expect(gl.deleteProgram.mock.calls).toEqual([[gl.createProgram.mock.results[0].value]]);
      expect(gl.deleteShader.mock.calls.map(([shader]) => shader)).toEqual(
        gl.createShader.mock.results.map(result => result.value)
      );
      expect(gl.createBuffer).not.toHaveBeenCalled();
      expect(gl.createTexture).not.toHaveBeenCalled();
    }
  );

  it('releases a rejected shader program before allocating buffers or textures', () => {
    const { gl, mesh } = materialDriver();
    gl.getProgramParameter.mockReturnValueOnce(false);
    expect(createMeshGpu(document.createElement('canvas'), gl, mesh)).toBeNull();
    expect(gl.deleteProgram).toHaveBeenCalledExactlyOnceWith(
      gl.createProgram.mock.results[0].value
    );
    expect(gl.deleteShader).toHaveBeenCalledTimes(2);
    expect(gl.createBuffer).not.toHaveBeenCalled();
    expect(gl.createTexture).not.toHaveBeenCalled();
  });

  it.each(['vertex-buffer', 'index-buffer', 'body-texture'] as const)(
    'releases every allocated object when context loss rejects the %s',
    missing => {
      const { gl, mesh } = materialDriver();
      if (missing === 'vertex-buffer') gl.createBuffer.mockReturnValueOnce(null);
      if (missing === 'index-buffer')
        gl.createBuffer.mockReturnValueOnce({}).mockReturnValueOnce(null);
      if (missing === 'body-texture') gl.createTexture.mockReturnValueOnce(null);
      expect(createMeshGpu(document.createElement('canvas'), gl, mesh)).toBeNull();
      expect(gl.deleteBuffer.mock.calls.map(([buffer]) => buffer)).toEqual(
        gl.createBuffer.mock.results.map(result => result.value)
      );
      expect(gl.deleteTexture).toHaveBeenCalledExactlyOnceWith(
        gl.createTexture.mock.results[0].value
      );
      expect(gl.deleteProgram).toHaveBeenCalledExactlyOnceWith(
        gl.createProgram.mock.results[0].value
      );
      expect(gl.bufferData).not.toHaveBeenCalled();
      expect(gl.drawElements).not.toHaveBeenCalled();
    }
  );

  it('keeps the alpha mask clamped when the source repeats and skips absent shader attributes', () => {
    const { gl, mesh, image, mask } = materialDriver();
    image.width = image.height = 128;
    gl.getAttribLocation.mockReturnValueOnce(0).mockReturnValueOnce(-1).mockReturnValueOnce(2);
    const gpu = createMeshGpu(document.createElement('canvas'), gl, mesh, true)!;
    gpu.upload(image, mask);
    const wrapping = gl.texParameteri.mock.calls.filter(
      ([, parameter]) => parameter === gl.TEXTURE_WRAP_S || parameter === gl.TEXTURE_WRAP_T
    );
    expect(wrapping).toEqual([
      [gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE],
      [gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE],
      [gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT],
      [gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT],
    ]);
    expect(gpu.draw({ yaw: 0, pitch: 0 })).toBe(true);
    expect(gl.enableVertexAttribArray.mock.calls).toEqual([[0], [2]]);
    expect(gl.vertexAttribPointer).toHaveBeenCalledTimes(2);
    gpu.dispose();
  });
});

function sourceFilm() {
  const mesh = {
    vertices: new Float32Array([
      0, 0, 0.3, 0, 0, 1, 0, 0, 1, 0, 0.3, 0, 0, 1, 0.5, 0, 1, 1, 0.3, 0, 0, 1, 0.5, 1, 0, 1, 0.3,
      0, 0, 1, 0, 1,
    ]),
    indices: new Uint16Array([0, 1, 2, 0, 2, 3]),
  };
  const mask = {
    width: 4,
    height: 3,
    alpha: new Uint8Array([255, 179, 255, 0, 180, 96, 0, 120, 0, 0, 255, 73]),
  };
  const pixels: ImageData = {
    data: new Uint8ClampedArray(mask.width * mask.height * 4),
    width: mask.width,
    height: mask.height,
    colorSpace: 'srgb',
  };
  const context: Pick<CanvasRenderingContext2D, 'createImageData' | 'putImageData'> = {
    // A Vitest mock has one call signature; accept both DOM overloads.
    createImageData: vi.fn<
      (source: number | ImageData, height?: number, settings?: ImageDataSettings) => ImageData
    >(() => pixels),
    putImageData:
      vi.fn<
        (
          data: ImageData,
          x: number,
          y: number,
          dirtyX?: number,
          dirtyY?: number,
          dirtyWidth?: number,
          dirtyHeight?: number
        ) => void
      >(),
  };
  return { mesh, mask, pixels, context };
}

describe('the alpha texture preserves source dimensions and the filtered film pixels', () => {
  it('serializes covered body, soft alpha and unmeshed opaque details without changing the source', () => {
    const { mesh, mask, pixels, context } = sourceFilm();
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
      configurable: true,
      value: () => context,
    });
    const original = mask.alpha.slice();
    const canvas = volumeFringeMask(mesh, mask);
    expect(canvas?.width).toBe(4);
    expect(canvas?.height).toBe(3);
    expect(context.createImageData).toHaveBeenCalledExactlyOnceWith(4, 3);
    expect(context.putImageData).toHaveBeenCalledExactlyOnceWith(pixels, 0, 0);
    expect([...pixels.data.filter((_value, index) => index % 4 === 3)]).toEqual([
      0, 179, 255, 0, 0, 96, 0, 120, 0, 0, 255, 73,
    ]);
    expect(pixels.data.filter((_value, index) => index % 4 !== 3).every(value => value === 0)).toBe(
      true
    );
    expect(mask.alpha).toEqual(original);
  });

  it('returns the baked fallback when Canvas2D is unavailable', () => {
    const { mesh, mask } = sourceFilm();
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
      configurable: true,
      value: () => null,
    });
    expect(volumeFringeMask(mesh, mask)).toBeNull();
  });

  it('returns the baked fallback when allocating image data is rejected', () => {
    const { mesh, mask, context } = sourceFilm();
    context.createImageData = vi.fn(() => {
      throw new RangeError('Image data allocation rejected');
    });
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
      configurable: true,
      value: () => context,
    });
    expect(volumeFringeMask(mesh, mask)).toBeNull();
    expect(context.putImageData).not.toHaveBeenCalled();
  });
});

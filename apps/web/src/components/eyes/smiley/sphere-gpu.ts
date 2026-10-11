/** One native WebGL1 scene; conditional cloth shares the existing sphere's depth. */
import type { ChannelValues } from '../rig/channels';
import { finite, spherePose } from './sphere-geometry';
import {
  SPHERE_DEPTH_FRAGMENT,
  SPHERE_FRAGMENT,
  SPHERE_QUAD,
  SPHERE_VERTEX,
} from './sphere-shaders';
import { sphereDepthGraphics, type SphereDepthGraphics } from './sphere-depth';
import { sphereClothGraphics } from './sphere-cloth';
import { createClothGpu, type ClothGraphics } from '../volume/cloth-gpu';
import { SMILEY_COLLAR } from '../volume/cloth-geometry';
import type { SpiritVariant } from '@/components/spirit/catalogue';

export type SphereGraphics = Pick<
  WebGLRenderingContext,
  | 'VERTEX_SHADER'
  | 'FRAGMENT_SHADER'
  | 'LINK_STATUS'
  | 'ARRAY_BUFFER'
  | 'STATIC_DRAW'
  | 'FLOAT'
  | 'TRIANGLES'
  | 'createShader'
  | 'shaderSource'
  | 'compileShader'
  | 'deleteShader'
  | 'attachShader'
  | 'linkProgram'
  | 'getProgramParameter'
  | 'deleteProgram'
  | 'deleteBuffer'
  | 'bindBuffer'
  | 'bufferData'
  | 'useProgram'
  | 'getAttribLocation'
  | 'enableVertexAttribArray'
  | 'vertexAttribPointer'
  | 'getUniformLocation'
  | 'uniform4fv'
  | 'uniform1f'
  | 'viewport'
  | 'drawArrays'
  | 'flush'
> &
  Partial<SphereDepthGraphics> &
  Partial<Omit<ClothGraphics, 'createProgram' | 'createBuffer' | 'createTexture'>> & {
    /** Context loss can make these allocations unavailable even on newer DOM typings. */
    createProgram(): WebGLProgram | null;
    createBuffer(): WebGLBuffer | null;
    createTexture?(): WebGLTexture | null;
  };

export interface SphereGpu {
  draw(values: Readonly<ChannelValues>, visible?: boolean): boolean;
  reset(): void;
  dispose(): void;
}

function programFor(gl: SphereGraphics, depth: boolean): WebGLProgram | null {
  const shaders = [gl.createShader(gl.VERTEX_SHADER), gl.createShader(gl.FRAGMENT_SHADER)];
  const sources = [SPHERE_VERTEX, depth ? SPHERE_DEPTH_FRAGMENT : SPHERE_FRAGMENT];
  const program = gl.createProgram();
  if (shaders.some(shader => !shader) || !program) {
    shaders.forEach(shader => gl.deleteShader(shader));
    gl.deleteProgram(program);
    return null;
  }
  shaders.forEach((shader, index) => {
    if (!shader) return;
    gl.shaderSource(shader, sources[index]);
    gl.compileShader(shader);
    gl.attachShader(program, shader);
  });
  gl.linkProgram(program);
  shaders.forEach(shader => gl.deleteShader(shader));
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    gl.deleteProgram(program);
    return null;
  }
  return program;
}

function refreshCache(
  state: Float32Array,
  previous: Float64Array,
  cool: number,
  cold: number,
  sway: number
): boolean {
  let changed =
    Math.abs(cool - previous[4]) >= 0.0001 ||
    Number.isNaN(previous[4]) ||
    Math.abs(cold - previous[5]) >= 0.0001 ||
    Math.abs(sway - previous[6]) >= 0.0001;
  for (let index = 0; index < 4; index++) {
    if (Math.abs(state[index] - previous[index]) < 0.0001) continue;
    previous[index] = state[index];
    changed = true;
  }
  if (changed) {
    previous[4] = cool;
    previous[5] = cold;
    previous[6] = sway;
  }
  return changed;
}

export function createSphereGpu(
  canvas: HTMLCanvasElement,
  gl: SphereGraphics,
  variant: SpiritVariant = 'male',
  onTextureReady: () => void = () => {}
): SphereGpu | null {
  const depth = sphereDepthGraphics(gl);
  const clothGraphics = depth ? sphereClothGraphics(gl) : null;
  const program = programFor(gl, Boolean(depth));
  if (!program) return null;
  const buffer = gl.createBuffer();
  if (!buffer) {
    gl.deleteProgram(program);
    return null;
  }
  gl.useProgram(program);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, SPHERE_QUAD, gl.STATIC_DRAW);
  const attribute = gl.getAttribLocation(program, 'a_point');
  gl.enableVertexAttribArray(attribute);
  gl.vertexAttribPointer(attribute, 2, gl.FLOAT, false, 0, 0);
  const stateLocation = gl.getUniformLocation(program, 'u_state');
  const coolLocation = gl.getUniformLocation(program, 'u_cool');
  const pixelLocation = gl.getUniformLocation(program, 'u_pixel');
  gl.viewport(0, 0, canvas.width, canvas.height);
  gl.uniform1f(pixelLocation, 2 / canvas.width);
  gl.uniform1f(gl.getUniformLocation(program, 'u_female'), Number(variant === 'female'));
  const state = new Float32Array(4);
  const previous = new Float64Array(7).fill(NaN);
  let active = true;
  let cloth: ReturnType<typeof createClothGpu> | null = null;
  let scarfReady = false;
  const syncCloth = (cold: number, visible: boolean) => {
    if (!visible || cold <= 0.02) {
      cloth?.dispose();
      cloth = null;
      scarfReady = false;
    } else if (!cloth && clothGraphics) {
      cloth = createClothGpu(canvas, clothGraphics, SMILEY_COLLAR, () => {
        if (!active) return;
        previous.fill(NaN);
        onTextureReady();
      });
    }
  };
  const paintBody = (cool: number) => {
    gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.enableVertexAttribArray(attribute);
    gl.vertexAttribPointer(attribute, 2, gl.FLOAT, false, 0, 0);
    if (depth) {
      depth.enable(depth.DEPTH_TEST);
      depth.depthFunc(depth.LEQUAL);
      gl.depthMask?.(true);
      depth.clearDepth(1);
      depth.clearColor(0, 0, 0, 0);
      depth.clear(depth.COLOR_BUFFER_BIT | depth.DEPTH_BUFFER_BIT);
    }
    gl.uniform4fv(stateLocation, state);
    gl.uniform1f(coolLocation, cool);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  };
  const paintCloth = (values: Readonly<ChannelValues>, pose: ReturnType<typeof spherePose>) => {
    if (cloth && clothGraphics) {
      clothGraphics.enable(clothGraphics.BLEND);
      clothGraphics.blendFunc(clothGraphics.ONE, clothGraphics.ONE_MINUS_SRC_ALPHA);
    }
    return cloth?.draw(values, pose) ?? false;
  };
  return {
    reset() {
      previous.fill(NaN);
    },
    draw(values, visible = true) {
      if (!active) return false;
      const cold = clothGraphics ? Math.max(0, Math.min(1, finite(values.weatherCold))) : 0;
      syncCloth(cold, visible);
      if (!visible) {
        previous.fill(NaN);
        return false;
      }
      const pose = spherePose(values);
      state[0] = pose.yaw;
      state[1] = pose.pitch;
      state[2] = (finite(values.tilt) * Math.PI) / 180;
      state[3] = finite(values.lightWarm);
      const cool = finite(values.lightCool);
      const sway = cloth ? finite(values.ambientSway) : 0;
      if (!refreshCache(state, previous, cool, cold, sway)) return scarfReady;
      paintBody(cool);
      scarfReady = paintCloth(values, pose);
      gl.flush();
      return scarfReady;
    },
    dispose() {
      if (!active) return;
      active = false;
      cloth?.dispose();
      cloth = null;
      gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
    },
  };
}

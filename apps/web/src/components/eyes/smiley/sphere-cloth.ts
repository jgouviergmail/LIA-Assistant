import type { SphereGraphics } from './sphere-gpu';
import type { ClothGraphics } from '../volume/cloth-gpu';

/** Old/no-depth drivers keep the sphere and its DOM band, without mesh allocations. */
export function sphereClothGraphics(gl: SphereGraphics): ClothGraphics | null {
  const functions = [
    'uniform2fv',
    'uniform1i',
    'createTexture',
    'deleteTexture',
    'bindTexture',
    'activeTexture',
    'texImage2D',
    'texParameteri',
    'blendFunc',
    'depthMask',
    'drawElements',
  ] as const;
  const constants = [
    'ELEMENT_ARRAY_BUFFER',
    'UNSIGNED_SHORT',
    'TEXTURE_2D',
    'TEXTURE0',
    'RGBA',
    'UNSIGNED_BYTE',
    'TEXTURE_MIN_FILTER',
    'TEXTURE_MAG_FILTER',
    'TEXTURE_WRAP_S',
    'TEXTURE_WRAP_T',
    'LINEAR',
    'REPEAT',
    'CLAMP_TO_EDGE',
    'BLEND',
    'ONE',
    'ONE_MINUS_SRC_ALPHA',
    'ALWAYS',
  ] as const;
  if (!functions.every(key => typeof gl[key] === 'function')) return null;
  if (!constants.every(key => Number.isFinite(gl[key]))) return null;
  return gl as ClothGraphics;
}

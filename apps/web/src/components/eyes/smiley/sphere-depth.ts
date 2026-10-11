/** A flat quad depth cannot occlude cloth; the ray-hit depth must be writable. */
export type SphereDepthGraphics = Pick<
  WebGLRenderingContext,
  | 'getContextAttributes'
  | 'DEPTH_TEST'
  | 'DEPTH_BUFFER_BIT'
  | 'COLOR_BUFFER_BIT'
  | 'LEQUAL'
  | 'enable'
  | 'depthFunc'
  | 'clearDepth'
  | 'clearColor'
  | 'clear'
> & { getExtension(name: 'EXT_frag_depth'): EXT_frag_depth | null };

export function sphereDepthGraphics(gl: Partial<SphereDepthGraphics>): SphereDepthGraphics | null {
  if (!gl.getExtension?.('EXT_frag_depth') || !gl.getContextAttributes?.()?.depth) return null;
  const functions = ['enable', 'depthFunc', 'clearDepth', 'clearColor', 'clear'] as const;
  const constants = ['DEPTH_TEST', 'DEPTH_BUFFER_BIT', 'COLOR_BUFFER_BIT', 'LEQUAL'] as const;
  if (!functions.every(key => typeof gl[key] === 'function')) return null;
  if (!constants.every(key => Number.isFinite(gl[key]))) return null;
  return gl as SphereDepthGraphics;
}

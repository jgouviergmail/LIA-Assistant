/** One alpha-only transfer for the native material and its SVG bake fallback. */
export function sourceAlphaTransfer(floor: number) {
  return {
    slope: 1 / (1 - floor),
    intercept: floor === 0 ? 0 : -floor / (1 - floor),
    // Source alpha 3 becomes 1/253 after removing the companion's alpha-2 matte.
    // Keep that detail with an exact power of two above WebGL1 mediump's
    // minimum positive range; zero must still discard before writing depth.
    cutoff: floor > 0 ? 1 / 4096 : 0.004,
  };
}

/** A subdivided front scarf retains its authored knot while following the body depth. */
import {
  volumeDepth,
  type CollarProfile,
  type VolumeMesh,
  type VolumeProfile,
} from './volume-geometry';
export const SMILEY_COLLAR: CollarProfile = {
  centerY: 0.65,
  radiusX: 1.13,
  radiusZ: 1.13,
  height: 0.18,
  conformSphereRadius: 1.274,
  tail: true,
};

function scarfDepth(profile: CollarProfile, surface?: VolumeProfile) {
  const depth = (x: number, y: number) => {
    if (surface) return volumeDepth(surface, x, y);
    if (profile.conformSphereRadius)
      return Math.sqrt(Math.max(0, profile.conformSphereRadius ** 2 - x * x - y * y));
    return (
      (profile.centerZ ?? 0) +
      profile.radiusZ * Math.sqrt(Math.max(0, 1 - (x / profile.radiusX) ** 2))
    );
  };
  const hangingRoom = depth(profile.radiusX * 0.72, profile.centerY) * 0.8;
  return (x: number, y: number) =>
    0.025 +
    Math.max(
      depth(x, y),
      profile.tail && x > profile.radiusX * 0.35 && y > profile.centerY ? hangingRoom : 0
    );
}

export function clothMesh(profile: CollarProfile, surface?: VolumeProfile): VolumeMesh {
  const columns = 20,
    rows = 24,
    width = profile.radiusX * 2.2,
    depth = scarfDepth(profile, surface),
    vertices: number[] = [],
    indices: number[] = [];
  for (let row = 0; row <= rows; row++)
    for (let column = 0; column <= columns; column++) {
      const u = column / columns,
        v = row / rows,
        x = (u - 0.5) * width,
        y = profile.centerY + (v - 0.54) * width,
        step = 0.002,
        nx = -(depth(x + step, y) - depth(x - step, y)) / (2 * step),
        ny = -(depth(x, y + step) - depth(x, y - step)) / (2 * step),
        length = Math.hypot(nx, ny, 1);
      vertices.push(x, y, depth(x, y), nx / length, ny / length, 1 / length, u, v);
    }
  for (let row = 0; row < rows; row++)
    for (let column = 0; column < columns; column++) {
      const a = row * (columns + 1) + column,
        b = a + 1,
        c = a + columns + 1,
        d = c + 1;
      indices.push(a, b, d, a, d, c);
    }
  return { vertices: new Float32Array(vertices), indices: new Uint16Array(indices) };
}

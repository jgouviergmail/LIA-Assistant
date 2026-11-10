/** Prepared front drapes or closed ribbons retain the authored knot and body fit. */
import {
  volumeDepth,
  type CollarProfile,
  type VolumeMesh,
  type VolumeProfile,
} from './volume-geometry';
import { mapScarfUv, SCARF_ART } from './scarf-fit';
import { scarfWrapFacets, scarfKnotFacets, type ScarfFacet } from './scarf-wrap';

function scarfDepth(profile: CollarProfile, surface?: VolumeProfile) {
  const depth = (x: number, y: number) => {
    if (surface) return volumeDepth(surface, x, y);
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
  if (profile.wrap) return scarfFacetMesh(scarfWrapFacets(profile));
  const columns = 20,
    // A row exactly at the fit seam prevents a triangle from interpolating
    // across two different vertical texture scales.
    rowUvs = [...Array.from({ length: 25 }, (_, row) => row / 24), SCARF_ART.tailStart].sort(
      (a, b) => a - b
    ),
    rows = rowUvs.length - 1,
    depth = scarfDepth(profile, surface),
    vertices: number[] = [],
    indices: number[] = [];
  for (let row = 0; row <= rows; row++)
    for (let column = 0; column <= columns; column++) {
      const u = column / columns,
        v = rowUvs[row],
        { x, y } = mapScarfUv(profile, u, v),
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

export function scarfKnotMesh(profile: CollarProfile): VolumeMesh {
  return scarfFacetMesh(scarfKnotFacets(profile));
}

function scarfFacetMesh(facets: readonly ScarfFacet[]): VolumeMesh {
  const vertices: number[] = [],
    indices: number[] = [];
  for (const { origin: p, horizontal: h, height, uv } of facets) {
    const a = vertices.length / 8;
    const length = Math.hypot(h.x, h.z);
    for (const [s, t] of [
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
    ]) {
      vertices.push(
        p.x + h.x * s,
        p.y + h.y * s + height * t,
        p.z + h.z * s,
        -h.z / length,
        0,
        h.x / length,
        uv.left + (uv.right - uv.left) * s,
        uv.top + (uv.bottom - uv.top) * t
      );
    }
    indices.push(a, a + 1, a + 2, a, a + 2, a + 3);
  }
  return { vertices: new Float32Array(vertices), indices: new Uint16Array(indices) };
}

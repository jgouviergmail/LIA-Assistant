/** Prepared garment facets shared verbatim by native WebGL and CSS fallback. */
import { SCARF_ART, type ScarfFit } from './scarf-fit';

export const SCARF_WRAP_SEGMENTS = 32;
export const SCARF_KNOT_UV = { left: 0.76, top: 0.32, right: 1, bottom: 0.78 } as const;
export interface ScarfPoint {
  x: number;
  y: number;
  z: number;
}
export interface ScarfFacet {
  origin: ScarfPoint;
  horizontal: ScarfPoint;
  height: number;
  uv: { left: number; top: number; right: number; bottom: number };
}

/** A superellipse follows a boxy shell or a round body without a front-only end. */
export function scarfWrapPoint(fit: ScarfFit, angle: number): ScarfPoint {
  const wrap = fit.wrap!;
  const sine = Math.sin(angle),
    cosine = Math.cos(angle);
  const signedPower = (value: number) => Math.sign(value) * Math.abs(value) ** (2 / wrap.power);
  return {
    x: fit.radiusX * signedPower(sine),
    y: fit.centerY + wrap.frontDrop * cosine,
    z: wrap.radiusZ * signedPower(cosine),
  };
}

export function scarfWrapFacets(fit: ScarfFit): ScarfFacet[] {
  if (!fit.wrap) return [];
  return Array.from({ length: SCARF_WRAP_SEGMENTS }, (_, index) => {
    const a = scarfWrapPoint(fit, (index / SCARF_WRAP_SEGMENTS) * Math.PI * 2);
    const b = scarfWrapPoint(fit, ((index + 1) / SCARF_WRAP_SEGMENTS) * Math.PI * 2);
    return {
      origin: { x: a.x, y: a.y - fit.height / 2, z: a.z },
      horizontal: { x: b.x - a.x, y: b.y - a.y, z: b.z - a.z },
      height: fit.height,
      // This measured swatch retains the authored rounded woven edges and
      // shading. Its alpha is continuous at both ends; no painted tip survives.
      uv: {
        left: (index % 2 ? 100 : 88) / 192,
        top: 87.5 / 192,
        right: (index % 2 ? 88 : 100) / 192,
        bottom: 123.5 / 192,
      },
    };
  });
}

/** The original authored knot and free end retain their aspect and colours. */
export function scarfKnotFacet(fit: ScarfFit): ScarfFacet {
  const wrap = fit.wrap!;
  const angle = Math.asin(0.68 ** (wrap.power / 2));
  const point = scarfWrapPoint(fit, angle);
  const width = (SCARF_KNOT_UV.right - SCARF_KNOT_UV.left) * wrap.knotScale;
  return {
    origin: { x: point.x - width / 2, y: point.y - fit.height * 0.75, z: point.z + 0.045 },
    horizontal: { x: width, y: 0, z: 0 },
    height: (SCARF_KNOT_UV.bottom - SCARF_KNOT_UV.top) * wrap.knotScale,
    uv: SCARF_KNOT_UV,
  };
}

/** Subdivide the same source plane below the attached part of the knot. */
export function scarfKnotFacets(fit: ScarfFit): readonly [ScarfFacet, ScarfFacet] {
  const knot = scarfKnotFacet(fit);
  const sourceHeight = knot.uv.bottom - knot.uv.top;
  // The knot starts 3/4 band heights above the band center and the band
  // extends another 1/2 height below it.
  const bandEdge = fit.height * 1.25;
  const tailStart = Math.max(
    SCARF_ART.tailStart,
    knot.uv.top + (bandEdge / knot.height) * sourceHeight
  );
  const attachedHeight = (knot.height * (tailStart - knot.uv.top)) / sourceHeight;
  return [
    { ...knot, height: attachedHeight, uv: { ...knot.uv, bottom: tailStart } },
    {
      ...knot,
      origin: { ...knot.origin, y: knot.origin.y + attachedHeight },
      height: knot.height - attachedHeight,
      uv: { ...knot.uv, top: tailStart },
    },
  ];
}

/** Static patch dimensions and basis; CSS composes the head pose on the same box. */
export function scarfFacetStyle(facet: ScarfFacet) {
  const { origin: p, horizontal: h, uv } = facet;
  const width = Math.hypot(h.x, h.y, h.z);
  const length = Math.hypot(h.x, h.z);
  const position = (start: number, end: number) =>
    start === 0 ? 0 : (start / (1 - end + start)) * 100;
  const left = Math.min(uv.left, uv.right),
    right = Math.max(uv.left, uv.right);
  return {
    '--scarf-facet-width': `${width}em`,
    '--scarf-facet-height': `${facet.height}em`,
    '--scarf-facet-transform': `translate3d(${p.x}em, ${p.y}em, ${p.z}em) matrix3d(${h.x / width},${h.y / width},${h.z / width},0,0,1,0,0,${-h.z / length},0,${h.x / length},0,0,0,0,1)`,
    backgroundSize: `${100 / (right - left)}% ${100 / (uv.bottom - uv.top)}%`,
    backgroundPosition: `${position(left, right)}% ${position(uv.top, uv.bottom)}%`,
    '--scarf-u-direction': uv.left < uv.right ? 1 : -1,
  };
}

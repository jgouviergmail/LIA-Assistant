import type { AnchorPosition } from './useEyesAnchor';

interface Size {
  width: number;
  height: number;
}
interface Viewport extends Size {
  minimumTop: number;
}
interface Obstacle {
  left: number;
  top: number;
  right: number;
  bottom: number;
}
const MARGIN = 8;

function intersects(point: AnchorPosition, size: Size, rect: Obstacle) {
  return (
    point.left < rect.right + MARGIN &&
    point.left + size.width > rect.left - MARGIN &&
    point.top < rect.bottom + MARGIN &&
    point.top + size.height > rect.top - MARGIN
  );
}

function inside(
  point: AnchorPosition,
  minLeft: number,
  maxLeft: number,
  minTop: number,
  maxTop: number
) {
  return (
    point.left >= minLeft && point.left <= maxLeft && point.top >= minTop && point.top <= maxTop
  );
}

/** Keep a default companion out of live controls; explicit user positions stay owned. */
export function unobstructedPlacement(
  preferred: AnchorPosition,
  size: Size,
  viewport: Viewport,
  obstacles: readonly Obstacle[]
): AnchorPosition | null {
  const minLeft = MARGIN;
  const maxLeft = viewport.width - size.width - MARGIN;
  const maxTop = viewport.height - size.height - MARGIN;
  const minTop = Math.max(MARGIN, viewport.minimumTop);
  if (maxLeft < minLeft || maxTop < minTop) return null;
  const clamped = {
    left: Math.min(maxLeft, Math.max(minLeft, preferred.left)),
    top: Math.min(maxTop, Math.max(minTop, preferred.top)),
  };
  const xs = [clamped.left, maxLeft, minLeft, (maxLeft + minLeft) / 2];
  const ys = [clamped.top, maxTop, minTop, (maxTop + minTop) / 2];
  // Probe the four reference columns/rows at control boundaries. Avoid a
  // Cartesian product of every control edge on a dense settings page.
  const candidates = ys.flatMap(top => xs.map(left => ({ left, top })));
  for (const rect of obstacles) {
    for (const top of [rect.bottom + MARGIN, rect.top - size.height - MARGIN]) {
      candidates.push(...xs.map(left => ({ left, top })));
    }
    for (const left of [rect.right + MARGIN, rect.left - size.width - MARGIN]) {
      candidates.push(...ys.map(top => ({ left, top })));
    }
  }
  for (const point of candidates) {
    if (!inside(point, minLeft, maxLeft, minTop, maxTop)) continue;
    if (!obstacles.some(rect => intersects(point, size, rect))) return point;
  }
  return null;
}

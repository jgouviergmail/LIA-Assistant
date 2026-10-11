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

function inside(point: AnchorPosition, maxLeft: number, minTop: number, maxTop: number) {
  return (
    point.left >= MARGIN && point.left <= maxLeft && point.top >= minTop && point.top <= maxTop
  );
}

/** Keep a default companion out of live controls; explicit user positions stay owned. */
export function unobstructedPlacement(
  preferred: AnchorPosition,
  size: Size,
  viewport: Viewport,
  obstacles: readonly Obstacle[]
): AnchorPosition | null {
  const maxLeft = viewport.width - size.width - MARGIN;
  const maxTop = viewport.height - size.height - MARGIN;
  const minTop = Math.max(MARGIN, viewport.minimumTop);
  if (maxLeft < MARGIN || maxTop < minTop) return null;
  const xs = [preferred.left, maxLeft, MARGIN, (maxLeft + MARGIN) / 2];
  const ys = [preferred.top, maxTop, minTop, (maxTop + minTop) / 2];
  for (const top of ys) {
    for (const left of xs) {
      if (!inside({ left, top }, maxLeft, minTop, maxTop)) continue;
      const blocked = obstacles.some(rect => intersects({ left, top }, size, rect));
      if (!blocked) return { left, top };
    }
  }
  return null;
}

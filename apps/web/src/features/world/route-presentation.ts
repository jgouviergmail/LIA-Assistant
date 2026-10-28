/** Read-only bounded projection of the navigator's current path. */
import { project } from './geometry';
import type { Point } from './types';

export function routePresentation(
  origin: Point,
  path: readonly Point[],
  enabled: boolean
): readonly Point[] {
  if (!enabled || !path.length || !Number.isFinite(origin.x + origin.y)) return [];
  const route = path.slice(0, 128);
  if (route.some(point => !Number.isFinite(point.x + point.y))) return [];
  return [origin, ...route];
}
export function paintRoute(
  c: CanvasRenderingContext2D,
  origin: Point,
  path: readonly Point[],
  enabled: boolean
): void {
  const points = routePresentation(origin, path, enabled);
  if (!points.length) return;
  c.save();
  c.strokeStyle = '#fff2ce';
  c.globalAlpha = 0.85;
  c.lineWidth = 2;
  c.setLineDash([4, 7]);
  c.beginPath();
  points.forEach((point, index) => {
    const p = project(point);
    if (index) c.lineTo(p.x, p.y);
    else c.moveTo(p.x, p.y);
  });
  c.stroke();
  c.restore();
}

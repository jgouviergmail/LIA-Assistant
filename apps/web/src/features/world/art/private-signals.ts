/** A local count/unavailability badge; its input cannot contain text or entity IDs. */
import { project } from '../geometry';
import type { Point, Rect, WorldProp } from '../types';
import type { PrivateSignalPresentation } from '../private-signal-projection';
export function privateSignalBounds(prop: WorldProp): Rect {
  const at = project({ x: prop.x + prop.width / 2, y: prop.y + prop.depth / 2 }, prop.height);
  return { x: at.x + 1, y: at.y - 16, width: 25, height: 20 };
}
export function hitsPrivateSignal(prop: WorldProp, point: Point): boolean {
  const b = privateSignalBounds(prop);
  if (point.x < b.x || point.x > b.x + b.width || point.y < b.y || point.y > b.y + b.height)
    return false;
  const x = Math.max(b.x + 7, Math.min(b.x + b.width - 7, point.x));
  const y = Math.max(b.y + 7, Math.min(b.y + b.height - 7, point.y));
  return (point.x - x) ** 2 + (point.y - y) ** 2 <= 49;
}
export function paintPrivateSignal(
  c: CanvasRenderingContext2D,
  prop: WorldProp,
  signal: PrivateSignalPresentation
): void {
  const b = privateSignalBounds(prop);
  const label =
    signal.status === 'unavailable'
      ? '?'
      : signal.count !== null && signal.count > 99
        ? '99+'
        : String(signal.count);
  c.save();
  c.translate(b.x + 12, b.y + 10);
  c.fillStyle = '#f8f3e8';
  c.strokeStyle = '#235d68';
  c.lineWidth = 1.5;
  c.beginPath();
  c.roundRect(-12, -10, 25, 20, 7);
  c.fill();
  c.stroke();
  c.fillStyle = '#194652';
  c.font = '700 11px system-ui, sans-serif';
  c.textAlign = 'center';
  c.textBaseline = 'middle';
  c.fillText(label, 0, 0);
  c.restore();
}

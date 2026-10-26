import { project } from '../geometry';
import type { WorldProp } from '../types';
/** Ground footprint only, painted before furniture. Object colours are never altered. */
export function paintHoverFootprint(c: CanvasRenderingContext2D, prop: WorldProp): void {
  const corners = [
    { x: prop.x, y: prop.y },
    { x: prop.x + prop.width, y: prop.y },
    { x: prop.x + prop.width, y: prop.y + prop.depth },
    { x: prop.x, y: prop.y + prop.depth },
  ];
  c.save();
  c.beginPath();
  corners.forEach((corner, i) => {
    const p = project(corner);
    if (i) c.lineTo(p.x, p.y);
    else c.moveTo(p.x, p.y);
  });
  c.closePath();
  c.clip();
  c.fillStyle = 'rgba(148,226,204,.14)';
  c.strokeStyle = 'rgba(201,255,233,.68)';
  c.lineWidth = 1.2;
  c.fill();
  c.stroke();
  c.restore();
}

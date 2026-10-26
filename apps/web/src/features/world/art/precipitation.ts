import { isSheltered } from '../shelter';
import { project, screenToWorld } from '../geometry';
import type { Camera, Quality, WorldDefinition } from '../types';

/** Two depth layers, deterministic seeds, no per-frame textures or retained particles. */
export function paintPrecipitation(
  c: CanvasRenderingContext2D,
  world: WorldDefinition,
  camera: Camera,
  time: number,
  quality: Quality,
  rain: boolean
): void {
  const count = quality === 'low' ? 32 : quality === 'high' ? 120 : 72;
  c.save();
  c.lineCap = 'round';
  for (let layer = 0; layer < 2; layer++) {
    const speed = rain ? 210 + layer * 125 : 15 + layer * 8;
    c.strokeStyle = layer ? 'rgba(211,236,243,.58)' : 'rgba(168,210,225,.30)';
    c.fillStyle = 'rgba(249,250,243,.72)';
    c.lineWidth = layer ? 1.15 : 0.7;
    c.beginPath();
    for (let i = layer; i < count; i += 2) {
      const x =
        ((((i * 173 - time * (rain ? 48 : 6)) % (camera.width + 60)) + camera.width + 60) %
          (camera.width + 60)) -
        30;
      const y = ((i * 97 + speed * time) % (camera.height + 60)) - 30;
      const length = rain ? 8 + layer * 7 + (i % 4) : 2;
      if (
        isSheltered(world, screenToWorld({ x, y }, camera)) ||
        isSheltered(world, screenToWorld({ x: x - 3, y: y + length }, camera))
      )
        continue;
      if (rain) {
        c.moveTo(x, y);
        c.lineTo(x - length * 0.19, y + length);
      } else {
        c.moveTo(x + 1.5, y);
        c.arc(x, y, 1.5, 0, Math.PI * 2);
      }
    }
    if (rain) c.stroke();
    else c.fill();
  }
  if (rain) paintSplashes(c, world, camera, time, quality);
  c.restore();
}

/** Impacts are anchored to world tiles, so they stay put while the camera pans. */
function paintSplashes(
  c: CanvasRenderingContext2D,
  world: WorldDefinition,
  camera: Camera,
  time: number,
  quality: Quality
): void {
  const center = screenToWorld({ x: camera.width / 2, y: camera.height / 2 }, camera);
  const count = quality === 'low' ? 10 : 24;
  const baseX = Math.floor(center.x / 8) * 8,
    baseY = Math.floor(center.y / 8) * 8;
  c.strokeStyle = 'rgba(205,234,238,.46)';
  c.lineWidth = 0.8;
  for (let i = 0; i < count; i++) {
    const at = { x: baseX + ((i * 17) % 23) - 9 + 0.4, y: baseY + ((i * 13) % 23) - 9 + 0.6 };
    if (
      at.x < 0 ||
      at.y < 0 ||
      at.x >= world.width ||
      at.y >= world.height ||
      isSheltered(world, at)
    )
      continue;
    const p = project(at),
      x = (p.x - camera.center.x) * camera.zoom + camera.width / 2,
      y = (p.y - camera.center.y) * camera.zoom + camera.height / 2;
    if (x < 8 || y < 8 || x > camera.width - 8 || y > camera.height - 8) continue;
    const phase = (time * 1.35 + (at.x * 0.37 + at.y * 0.61)) % 1;
    c.globalAlpha = (1 - phase) * 0.8;
    c.beginPath();
    c.ellipse(
      x,
      y,
      (1 + phase * 5) * camera.zoom,
      (0.5 + phase * 2) * camera.zoom,
      0,
      0,
      Math.PI * 2
    );
    c.stroke();
    if (phase < 0.3) {
      c.beginPath();
      c.moveTo(x - 2, y - 1);
      c.lineTo(x - 3, y - 3);
      c.moveTo(x + 2, y - 1);
      c.lineTo(x + 3, y - 4);
      c.stroke();
    }
  }
}

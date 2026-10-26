import { project } from '../geometry';
import type { Camera, GroundPatch, Quality, WorldDefinition } from '../types';
const ponds = new WeakMap<WorldDefinition['grounds'], readonly GroundPatch[]>();
/** A handful of ground-anchored ripples; no particles, timers or retained animation state. */
export function paintPondMotion(
  c: CanvasRenderingContext2D,
  world: WorldDefinition,
  camera: Camera,
  time: number,
  quality: Quality,
  reduced: boolean
): void {
  if (reduced) return;
  let patches = ponds.get(world.grounds);
  if (!patches) {
    patches = world.grounds.filter(g => g.kind === 'water');
    ponds.set(world.grounds, patches);
  }
  if (!patches.length) return;
  c.save();
  c.strokeStyle = '#c1e5d7';
  c.lineWidth = 0.75;
  const count = quality === 'low' ? 2 : 4;
  for (let i = 0; i < count; i++) {
    const patch = patches[(i * 3 + 1) % patches.length];
    const p = project({
      x: patch.x + patch.width * (0.25 + (i % 2) * 0.4),
      y: patch.y + patch.height * 0.5,
    });
    const sx = (p.x - camera.center.x) * camera.zoom + camera.width / 2,
      sy = (p.y - camera.center.y) * camera.zoom + camera.height / 2;
    if (sx < -20 || sx > camera.width + 20 || sy < -20 || sy > camera.height + 20) continue;
    const phase = (time * 0.23 + i * 0.28) % 1;
    c.globalAlpha = (1 - phase) * 0.4;
    c.beginPath();
    c.ellipse(p.x, p.y, 3 + phase * 10, 1 + phase * 3, 0, 0, Math.PI * 2);
    c.stroke();
  }
  c.restore();
}

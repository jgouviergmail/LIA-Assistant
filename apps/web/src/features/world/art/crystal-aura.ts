import { project } from '../geometry';
import type { WorldProp } from '../types';
import type { Sprite } from './painter';

/** Baked once. A slow luminous breath and two tiny orbiting motes, never a flash. */
export function crystalAura(): Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 128;
  const c = canvas.getContext('2d');
  if (!c) throw new Error('Canvas unavailable');
  const gradient = c.createRadialGradient(64, 64, 0, 64, 64, 64);
  gradient.addColorStop(0, 'rgba(231,255,255,.95)');
  gradient.addColorStop(0.15, 'rgba(145,235,255,.72)');
  gradient.addColorStop(0.4, 'rgba(161,115,255,.34)');
  gradient.addColorStop(1, 'rgba(134,86,224,0)');
  c.fillStyle = gradient;
  c.fillRect(0, 0, 128, 128);
  return { canvas, width: 128, height: 128, anchorX: 64, anchorY: 64 };
}
export function paintCrystalAura(
  c: CanvasRenderingContext2D,
  prop: WorldProp,
  glow: Sprite,
  time: number,
  reduced: boolean
): void {
  const at = project({ x: prop.x + prop.width / 2, y: prop.y + prop.depth / 2 }, 1.62);
  c.save();
  c.globalCompositeOperation = 'screen';
  c.globalAlpha = reduced ? 0.67 : 0.67 + Math.sin(time * 0.65) * 0.08;
  c.drawImage(glow.canvas, at.x - 42, at.y - 42, 84, 84);
  if (!reduced)
    for (let i = 0; i < 2; i++) {
      const angle = time * 0.45 + i * Math.PI;
      c.fillStyle = '#e6fcff';
      c.globalAlpha = 0.62;
      c.beginPath();
      c.arc(at.x + Math.cos(angle) * 18, at.y + Math.sin(angle) * 9, 1, 0, Math.PI * 2);
      c.fill();
    }
  c.restore();
}

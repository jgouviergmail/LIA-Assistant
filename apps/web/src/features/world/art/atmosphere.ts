import { paintPrecipitation } from './precipitation';
import { coveredRectangles } from '../shelter';
import type { Atmosphere } from '../atmosphere';
import type { Camera, Quality, Rect, WorldDefinition, WorldProp } from '../types';
import { project } from '../geometry';
import { ambientStrength, nightColour, nightStrength } from './lighting';
import { canonicalSize, rotateModelPoint } from './model';
import type { Sprite } from './painter';

/** One cached radial texture serves ground pools and bulb bloom at different scales. */
export function paintLampGlow(): Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 160;
  const c = canvas.getContext('2d');
  if (!c) throw new Error('Canvas unavailable');
  const glow = c.createRadialGradient(80, 80, 0, 80, 80, 80);
  glow.addColorStop(0, 'rgba(255,250,219,.95)');
  glow.addColorStop(0.08, 'rgba(255,233,165,.85)');
  glow.addColorStop(0.26, 'rgba(255,203,105,.40)');
  glow.addColorStop(0.58, 'rgba(255,184,77,.12)');
  glow.addColorStop(1, 'rgba(255,184,77,0)');
  c.fillStyle = glow;
  c.fillRect(0, 0, 160, 160);
  return { canvas, width: 160, height: 160, anchorX: 80, anchorY: 80 };
}
function screenRect(c: CanvasRenderingContext2D, r: Rect, camera: Camera): void {
  const corners = [
    { x: r.x, y: r.y },
    { x: r.x + r.width, y: r.y },
    { x: r.x + r.width, y: r.y + r.height },
    { x: r.x, y: r.y + r.height },
  ];
  for (let i = 0; i < corners.length; i++) {
    const p = project(corners[i]),
      x = (p.x - camera.center.x) * camera.zoom + camera.width / 2,
      y = (p.y - camera.center.y) * camera.zoom + camera.height / 2;
    if (i) c.lineTo(x, y);
    else c.moveTo(x, y);
  }
  c.closePath();
}
function clipOutdoors(c: CanvasRenderingContext2D, world: WorldDefinition, camera: Camera): void {
  c.beginPath();
  c.rect(0, 0, camera.width, camera.height);
  for (const r of coveredRectangles(world)) screenRect(c, r, camera);
  c.clip('evenodd');
}

// Ground tint is clipped to the plateau: the star field is never painted over.
export function paintGroundShade(
  c: CanvasRenderingContext2D,
  world: WorldDefinition,
  camera: Camera,
  atmosphere: Atmosphere
): void {
  const outside = nightStrength(atmosphere.phase);
  if (!outside) return;
  const inside = ambientStrength(atmosphere.phase, true);
  c.save();
  c.beginPath();
  screenRect(c, { x: 0, y: 0, width: world.width, height: world.height }, camera);
  c.clip();
  c.fillStyle = nightColour(inside);
  c.fillRect(0, 0, camera.width, camera.height);
  clipOutdoors(c, world, camera);
  // Alpha composition gives exactly the outdoor level, not two stacked night tints.
  c.fillStyle = nightColour((outside - inside) / (1 - inside));
  c.fillRect(0, 0, camera.width, camera.height);
  c.restore();
}

function lightPosition(prop: WorldProp, ground: boolean) {
  if (prop.kind === 'lamp') return { x: prop.x + 0.21, y: prop.y + 0.21, z: ground ? 0 : 1.91 };
  if (prop.kind === 'tablelamp') {
    const { w, d } = canonicalSize(prop);
    const p = rotateModelPoint({ x: 0.3, y: 0.3, z: ground ? 0.85 : 1.3 }, w, d, prop.facing ?? 1);
    return { ...p, x: prop.x + p.x, y: prop.y + p.y };
  }
  return { x: prop.x + 0.45, y: prop.y + 0.45, z: 1.5 };
}
function drawGlow(
  c: CanvasRenderingContext2D,
  prop: WorldProp,
  camera: Camera,
  glow: Sprite,
  ground: boolean
): void {
  const p = lightPosition(prop, ground),
    at = project(p, p.z);
  const table = prop.kind === 'tablelamp';
  const w = (ground ? (table ? 100 : 250) : table ? 64 : 100) * camera.zoom;
  const h = ground ? w * 0.5 : w;
  const x = (at.x - camera.center.x) * camera.zoom + camera.width / 2;
  const y = (at.y - camera.center.y) * camera.zoom + camera.height / 2;
  if (x < -w || x > camera.width + w || y < -h || y > camera.height + h) return;
  c.drawImage(glow.canvas, x - w / 2, y - h / 2, w, h);
}
/** Pools precede furniture; source halos follow it, so light does not flatten silhouettes. */
export function paintGroundLights(
  c: CanvasRenderingContext2D,
  world: WorldDefinition,
  camera: Camera,
  atmosphere: Atmosphere,
  glow: Sprite | null
): void {
  if (!glow || !nightStrength(atmosphere.phase)) return;
  c.save();
  c.globalCompositeOperation = 'screen';
  c.globalAlpha = (nightStrength(atmosphere.phase) / 0.6) * 0.88;
  for (const prop of world.props) if (prop.kind === 'lamp') drawGlow(c, prop, camera, glow, true);
  c.restore();
}
function paintNight(
  c: CanvasRenderingContext2D,
  world: WorldDefinition,
  camera: Camera,
  atmosphere: Atmosphere,
  glow: Sprite | null
): void {
  if (!glow || !nightStrength(atmosphere.phase)) return;
  c.save();
  c.globalCompositeOperation = 'screen';
  c.globalAlpha = nightStrength(atmosphere.phase) / 0.6;
  for (const prop of world.props) {
    if (prop.kind !== 'lamp' && prop.kind !== 'tablelamp') continue;
    drawGlow(c, prop, camera, glow, false);
    if (prop.kind === 'tablelamp') {
      c.globalAlpha *= 0.55;
      drawGlow(c, prop, camera, glow, true);
      c.globalAlpha = nightStrength(atmosphere.phase) / 0.6;
    }
  }
  c.restore();
}

/** Cosmetic only, bounded particles, no flashes and no layout/authority mutations. */
export function paintAtmosphere(
  c: CanvasRenderingContext2D,
  world: WorldDefinition,
  camera: Camera,
  atmosphere: Atmosphere,
  time: number,
  quality: Quality,
  reduced: boolean,
  glow: Sprite | null
): void {
  paintNight(c, world, camera, atmosphere, glow);
  if (atmosphere.weather === 'fog') {
    c.save();
    clipOutdoors(c, world, camera);
    c.fillStyle = 'rgba(225,236,229,.10)';
    c.fillRect(0, 0, camera.width, camera.height);
    c.restore();
  }
  if (reduced || !['rain', 'snow'].includes(atmosphere.weather)) return;
  paintPrecipitation(c, world, camera, time, quality, atmosphere.weather === 'rain');
}

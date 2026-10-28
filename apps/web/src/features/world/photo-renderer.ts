/** An independent renderer receives only the allowlisted still, never the live simulation. */
import { LIA_PROJECT_SITE_URL } from '@/lib/project-attribution';
import { WORLD } from './definition';
import { WorldRenderer } from './renderer';
import { createSimulation } from './simulation';
import type { PhotoScene } from './photo-projection';
import type { Size } from './types';

export async function drawPhotoScene(scene: PhotoScene, size: Size, signal: AbortSignal) {
  signal.throwIfAborted();
  const canvas = document.createElement('canvas');
  const renderer = new WorldRenderer(
    canvas,
    WORLD,
    'low',
    { player: '', bip: '' },
    undefined,
    'photo',
    scene.decor
  );
  const dispose = () => renderer.destroy();
  try {
    const simulation = createSimulation(WORLD);
    simulation.player = { ...scene.player, position: { ...scene.player.position }, path: [] };
    simulation.bip = { ...scene.bip, position: { ...scene.bip.position }, path: [] };
    simulation.time = scene.time;
    renderer.reducedMotion = true;
    renderer.showRoute = false;
    renderer.setHome(scene.home);
    renderer.setSeason(scene.season);
    renderer.setAtmosphere(scene.atmosphere);
    renderer.resize(size.width, size.height);
    await renderer.preparePhoto(signal);
    signal.throwIfAborted();
    const scale = Math.max(size.width / scene.camera.width, size.height / scene.camera.height);
    renderer.render(
      {
        ...scene.camera,
        ...size,
        center: { ...scene.camera.center },
        zoom: scene.camera.zoom * scale,
      },
      simulation
    );
    paintWordmark(canvas);
    return { canvas, dispose };
  } catch (error) {
    dispose();
    throw error;
  }
}
/** The fixed signature, in device pixels: whatever transform or blend the scene left behind. */
function paintWordmark(canvas: HTMLCanvasElement) {
  const context = canvas.getContext('2d');
  if (!context) throw new Error('world_photo_unavailable');
  context.save();
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.globalAlpha = 1;
  context.globalCompositeOperation = 'source-over';
  context.shadowColor = 'transparent';
  const font = Math.max(18, Math.round(Math.max(canvas.width, canvas.height) / 50));
  context.font = `600 ${font}px system-ui, sans-serif`;
  context.textAlign = 'right';
  context.textBaseline = 'bottom';
  context.fillStyle = 'rgba(12,25,34,.8)';
  const signature = `LIA World - ${LIA_PROJECT_SITE_URL}`;
  const width = context.measureText(signature).width + font;
  context.fillRect(canvas.width - width - font / 2, canvas.height - font * 1.8, width, font * 1.4);
  context.fillStyle = '#ffffff';
  context.fillText(signature, canvas.width - font, canvas.height - font * 0.7);
  context.restore();
}

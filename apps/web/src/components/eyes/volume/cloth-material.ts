/** A single cloth texture owns its decoder and GPU allocation through teardown. */
import { createMeshGpu, type VolumeGraphics } from './mesh-gpu';
import type { VolumeMesh } from './volume-geometry';

export function createClothMaterial(
  canvas: HTMLCanvasElement,
  gl: VolumeGraphics,
  mesh: VolumeMesh,
  extent: number,
  url: string,
  onReady: () => void,
  onFailure: () => void
) {
  const gpu = createMeshGpu(canvas, gl, mesh, false, extent, false, 0, 'woven');
  if (!gpu) return null;
  let active = true,
    ready = false;
  const image = new Image();
  image.onload = () => {
    if (!active) return;
    gpu.upload(image);
    ready = true;
    onReady();
  };
  image.onerror = () => {
    if (active) onFailure();
  };
  image.src = url;
  return {
    gpu,
    ready: () => ready,
    dispose() {
      if (!active) return;
      active = false;
      image.onload = image.onerror = null;
      gpu.dispose();
    },
  };
}

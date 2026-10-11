/** The same authored alpha scarf shares either body scene, never another canvas/clock. */
import type { ChannelValues } from '../rig/channels';
import { WEATHER_COLD_MAX } from '../rig/ambient';
import { createMeshGpu, type VolumeGraphics } from './mesh-gpu';
import { clothMesh } from './cloth-geometry';
import {
  volumePose,
  type CollarProfile,
  type VolumePose,
  type VolumeProfile,
} from './volume-geometry';
export type ClothGraphics = VolumeGraphics;

export function createClothGpu(
  canvas: HTMLCanvasElement,
  gl: ClothGraphics,
  profile: CollarProfile,
  onTextureReady: () => void,
  extent = 1.3,
  surface?: VolumeProfile
) {
  let active = true,
    failed = false,
    ready = false;
  let gpu: ReturnType<typeof createMeshGpu> = null,
    image: HTMLImageElement | null = null;
  const stop = () => {
    if (image) {
      image.onload = null;
      image.onerror = null;
      image = null;
    }
    gpu?.dispose();
    gpu = null;
    ready = false;
  };
  return {
    draw(values: Readonly<ChannelValues>, pose: VolumePose = volumePose(values, 'orbit')): boolean {
      const cold = Number.isFinite(values.weatherCold)
        ? Math.max(0, Math.min(1, values.weatherCold))
        : 0;
      if (!active || failed) return false;
      if (cold <= 0.02) {
        stop();
        return false;
      }
      if (!gpu) {
        gpu = createMeshGpu(canvas, gl, clothMesh(profile, surface), false, extent);
        if (!gpu) {
          failed = true;
          return false;
        }
      }
      if (!image) {
        image = new Image();
        const material = image;
        image.onload = () => {
          if (!active || !gpu || image !== material) return;
          gpu.upload(material);
          ready = true;
          onTextureReady();
        };
        image.onerror = () => {
          if (image !== material) return;
          failed = true;
          stop();
        };
        image.src = '/avatars/scarf/v1/front.webp';
      }
      if (!ready) return false;
      // This mesh contains the authored front section only. Coarse body triangles
      // must not cut holes in a garment that follows the true front surface.
      gl.depthFunc(gl.ALWAYS);
      gl.depthMask(false);
      try {
        return gpu.draw(
          pose,
          values.lightWarm,
          values.lightCool,
          Math.min(1, cold / WEATHER_COLD_MAX)
        );
      } finally {
        gl.depthFunc(gl.LEQUAL);
        gl.depthMask(true);
      }
    },
    dispose() {
      if (!active) return;
      active = false;
      stop();
    },
  };
}

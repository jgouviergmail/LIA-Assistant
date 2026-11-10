/** Cloth shares the body canvas, pose and clock, with real rear-body occlusion. */
import type { ChannelValues } from '../rig/channels';
import type { VolumeGraphics } from './mesh-gpu';
import { clothMesh, scarfKnotMesh } from './cloth-geometry';
import { createClothMaterial } from './cloth-material';
import { mapScarfUv, SCARF_ART, scarfOpacity } from './scarf-fit';
import { scarfKnotFacets } from './scarf-wrap';
import {
  volumePose,
  type CollarProfile,
  type VolumePose,
  type VolumeProfile,
} from './volume-geometry';
export type ClothGraphics = VolumeGraphics;
type Material = NonNullable<ReturnType<typeof createClothMaterial>>;

export function createClothGpu(
  canvas: HTMLCanvasElement,
  gl: ClothGraphics,
  profile: CollarProfile,
  onTextureReady: () => void,
  extent = 1.3,
  surface?: VolumeProfile
) {
  const seamY = profile.wrap
    ? scarfKnotFacets(profile)[1].origin.y
    : mapScarfUv(profile, 0, SCARF_ART.tailStart).y;
  const drape = { shear: 0, seamY };
  let active = true,
    failed = false;
  const materials: Material[] = [];
  const stop = () => {
    for (const material of materials) material.dispose();
    materials.length = 0;
  };
  const fail = () => {
    failed = true;
    stop();
  };
  const prepare = () => {
    const specs = [{ mesh: clothMesh(profile, surface), url: SCARF_ART.url }];
    if (profile.wrap) specs.push({ mesh: scarfKnotMesh(profile), url: SCARF_ART.url });
    for (const { mesh, url } of specs) {
      const material = createClothMaterial(canvas, gl, mesh, extent, url, onTextureReady, fail);
      if (!material) {
        fail();
        return;
      }
      materials.push(material);
    }
  };
  return {
    draw(values: Readonly<ChannelValues>, pose: VolumePose = volumePose(values, 'orbit')): boolean {
      const opacity = scarfOpacity(values.weatherCold);
      if (!active || failed) return false;
      if (opacity === 0) {
        stop();
        return false;
      }
      if (materials.length === 0) prepare();
      if (failed || !materials.every(material => material.ready())) return false;
      drape.shear = values.scarfTrail;
      try {
        gl.depthFunc(profile.wrap ? gl.LEQUAL : gl.ALWAYS);
        gl.depthMask(Boolean(profile.wrap));
        materials[0].gpu.draw(
          pose,
          values.lightWarm,
          values.lightCool,
          opacity,
          undefined,
          profile.wrap ? undefined : drape
        );
        if (materials[1]) {
          gl.depthMask(false);
          materials[1].gpu.draw(
            pose,
            values.lightWarm,
            values.lightCool,
            opacity,
            undefined,
            drape
          );
        }
        return true;
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

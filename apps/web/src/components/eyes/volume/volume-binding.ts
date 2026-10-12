/** Resource lifetime follows the native rig's visibility/motion owner, no second observer/clock. */
import type { ChannelValues } from '../rig/channels';
import { restChannelValues } from '../rig/channels';
import type { SpiritVariant } from '@/components/spirit/catalogue';
import {
  companionBodyAsset,
  type CompanionCharacter,
} from '@/components/spirit/companion-catalogue';
import { createMeshGpu, type VolumeGraphics } from './mesh-gpu';
import {
  visibleVolumeMesh,
  volumePose,
  volumeProfile,
  type VolumeCharacter,
  type VolumeMask,
  type VolumeProfile,
  type VolumeMesh,
} from './volume-geometry';
import { createClothGpu } from './cloth-gpu';
import { readVolumeMask } from './volume-mask';
import { bodySurfaceProfile } from './volume-distance';
import { releaseNativeContext } from './context-lifetime';
import { volumeFringeMask, withSoftFringe } from './volume-fringe';

interface VolumeBinding {
  paint(values: Readonly<ChannelValues>, force?: boolean): boolean;
  visibility(visible: boolean): void;
  motion(reduced: boolean): void;
  reset(): void;
}
const painters = new WeakMap<HTMLElement, VolumeBinding>();
const snapshots = new WeakMap<HTMLElement, Readonly<ChannelValues>>();
const projections = new WeakMap<HTMLElement, (values: Readonly<ChannelValues>) => void>();
const materials = new WeakMap<HTMLElement, { profile: VolumeProfile; mask: VolumeMask }>();
export const bodyVolumeMaterial = (root: HTMLElement) => materials.get(root);
export function paintBodyVolume(root: HTMLElement, values: Readonly<ChannelValues>) {
  snapshots.set(root, values);
  return painters.get(root)?.paint(values) ?? false;
}
export function resetBodyVolume(root: HTMLElement) {
  painters.get(root)?.reset();
}
export function setBodyVolumeVisibility(root: HTMLElement, visible: boolean) {
  painters.get(root)?.visibility(visible);
}
export function setBodyVolumeReducedMotion(root: HTMLElement, reduced: boolean) {
  painters.get(root)?.motion(reduced);
}
export function bindVolumeProjection(
  root: HTMLElement,
  project: (values: Readonly<ChannelValues>) => void
) {
  projections.set(root, project);
  return () => {
    if (projections.get(root) === project) projections.delete(root);
  };
}

function nativeContext(canvas: HTMLCanvasElement): WebGLRenderingContext | null {
  if (typeof WebGLRenderingContext === 'undefined') return null;
  try {
    return canvas.getContext('webgl', {
      alpha: true,
      premultipliedAlpha: true,
      antialias: true,
      depth: true,
      stencil: false,
      preserveDrawingBuffer: false,
      powerPreference: 'low-power',
    });
  } catch {
    return null;
  }
}

export function bindBodyVolume(
  canvas: HTMLCanvasElement,
  root: HTMLElement,
  character: VolumeCharacter,
  variant: SpiritVariant,
  graphics?: VolumeGraphics | null
): () => void {
  let profile = volumeProfile(character, variant);
  let active = true,
    visible = root.dataset.rigVisible === 'true',
    reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  let gl: VolumeGraphics | null = null,
    nativeGl: WebGLRenderingContext | null = null,
    gpu: ReturnType<typeof createMeshGpu> = null,
    image: HTMLImageElement | null = null,
    cloth: ReturnType<typeof createClothGpu> | null = null;
  let mask: VolumeMask | null = null,
    mesh: VolumeMesh | null = null,
    fringe: HTMLCanvasElement | null = null,
    failed = false,
    loading = false,
    contextLost = false;
  const last = new Float64Array(6).fill(NaN);
  const ready = (value: boolean) => {
    root.dataset.volumeReady = String(value);
  };
  const stop = () => {
    gpu?.dispose();
    gpu = null;
    cloth?.dispose();
    cloth = null;
    ready(false);
    root.dataset.volumeScarfReady = 'false';
    last.fill(NaN);
    projections.get(root)?.(snapshots.get(root) ?? restChannelValues());
  };
  const paint = (values: Readonly<ChannelValues>, force = false) => {
    if (!active || !visible || reduced || document.hidden || !gl || !gpu) return false;
    const pose = volumePose(values, character),
      current = [
        pose.yaw,
        pose.pitch,
        values.lightWarm,
        values.lightCool,
        values.weatherCold,
        values.weatherCold > 0.02 ? values.ambientSway : 0,
      ];
    if (!force && current.every((value, index) => Math.abs(value - last[index]) < 0.0001))
      return root.dataset.volumeReady === 'true';
    last.set(current);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.depthMask(true);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const drawn = gpu.draw(pose, values.lightWarm, values.lightCool);
    ready(drawn);
    root.dataset.volumeScarfReady = String(drawn && (cloth?.draw(values, pose) ?? false));
    return drawn;
  };
  const redraw = () => {
    const values = snapshots.get(root) ?? restChannelValues();
    if (paint(values, true)) projections.get(root)?.(values);
  };
  const canStart = () =>
    active &&
    visible &&
    !reduced &&
    !document.hidden &&
    !gpu &&
    !failed &&
    !loading &&
    !contextLost;
  const start = () => {
    if (!canStart()) return;
    if (!image?.complete || !image.naturalWidth) {
      loading = true;
      image = new Image();
      image.onload = () => {
        loading = false;
        if (!active || !image) return;
        mask = readVolumeMask(image);
        if (!mask || !mask.alpha.some(alpha => alpha > 0)) {
          failed = true;
          return;
        }
        profile = bodySurfaceProfile(profile, mask);
        materials.set(root, { profile, mask });
        start();
      };
      image.onerror = () => {
        loading = false;
        failed = true;
        stop();
      };
      image.src =
        character === 'monitor'
          ? '/avatars/monitor/v2/body.webp'
          : companionBodyAsset(character as CompanionCharacter, variant);
      return;
    }
    if (!mask) return;
    if (graphics === undefined) {
      nativeGl = nativeContext(canvas);
      gl = nativeGl;
    } else gl = graphics;
    if (!gl) {
      failed = true;
      return;
    }
    if (!mesh) {
      const physical = visibleVolumeMesh(profile, mask);
      fringe = volumeFringeMask(physical, mask);
      mesh = withSoftFringe(physical, profile);
    }
    gpu = createMeshGpu(canvas, gl, mesh, false, 1.7, character === 'monitor');
    if (!gpu) {
      failed = true;
      return;
    }
    cloth = createClothGpu(canvas, gl, profile.collar, redraw, 1.7, profile);
    gpu.upload(image, fringe ?? undefined);
    redraw();
  };
  const binding: VolumeBinding = {
    paint,
    visibility(next) {
      visible = next;
      if (next) start();
      else stop();
    },
    motion(next) {
      reduced = next;
      if (next) stop();
      else start();
    },
    reset() {
      last.fill(NaN);
    },
  };
  painters.set(root, binding);
  ready(false);
  start();
  const lost = (event: Event) => {
    event.preventDefault();
    contextLost = true;
    stop();
  };
  const restored = () => {
    contextLost = false;
    start();
  };
  canvas.addEventListener('webglcontextlost', lost);
  canvas.addEventListener('webglcontextrestored', restored);
  return () => {
    if (!active) return;
    active = false;
    canvas.removeEventListener('webglcontextlost', lost);
    canvas.removeEventListener('webglcontextrestored', restored);
    if (image) {
      image.onload = null;
      image.onerror = null;
    }
    if (painters.get(root) === binding) {
      painters.delete(root);
      materials.delete(root);
    }
    stop();
    releaseNativeContext(nativeGl);
  };
}

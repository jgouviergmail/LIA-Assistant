/** Canvas lifetime is independent of the one native rig's animation clock. */
import type { ChannelValues } from '../rig/channels';
import { resolvePose } from '../rig/poses';
import { createSphereGpu, type SphereGraphics, type SphereGpu } from './sphere-gpu';
import type { SpiritVariant } from '@/components/spirit/catalogue';
import { releaseNativeContext } from '../volume/context-lifetime';

const painters = new WeakMap<HTMLElement, SphereGpu>();
const snapshots = new WeakMap<HTMLElement, Readonly<ChannelValues>>();

export function paintSmileySphere(root: HTMLElement, values: Readonly<ChannelValues>) {
  snapshots.set(root, values);
  root.dataset.volumeScarfReady = String(
    painters.get(root)?.draw(values, root.dataset.rigVisible !== 'false' && !document.hidden) ??
      false
  );
}

export function resetSmileySphere(root: HTMLElement) {
  painters.get(root)?.reset();
  root.dataset.volumeScarfReady = 'false';
}

function nativeContext(canvas: HTMLCanvasElement): WebGLRenderingContext | null {
  if (typeof WebGLRenderingContext === 'undefined') return null;
  try {
    return canvas.getContext('webgl', {
      alpha: true,
      premultipliedAlpha: true,
      antialias: false,
      depth: true,
      stencil: false,
      preserveDrawingBuffer: false,
      powerPreference: 'low-power',
    });
  } catch {
    return null;
  }
}

/** Context restoration is a browser event, never a timer or allocation retry loop. */
export function bindSmileySphere(
  canvas: HTMLCanvasElement,
  root: HTMLElement,
  graphics?: SphereGraphics | null,
  variant: SpiritVariant = root.dataset.smileyVariant === 'female' ? 'female' : 'male'
): () => void {
  const context = graphics === undefined ? nativeContext(canvas) : null;
  const driver = graphics === undefined ? context : graphics;
  const body = canvas.parentElement;
  let gpu: SphereGpu | null = null;
  let active = true;
  const ready = (value: boolean) => {
    if (body) body.dataset.sphereReady = String(value);
  };
  const stop = () => {
    if (painters.get(root) === gpu) painters.delete(root);
    gpu?.dispose();
    gpu = null;
    ready(false);
    root.dataset.volumeScarfReady = 'false';
  };
  const start = () => {
    if (!active || !driver || gpu) return;
    gpu = createSphereGpu(canvas, driver, variant, () => {
      if (!active) return;
      paintSmileySphere(root, snapshots.get(root) ?? resolvePose('neutral', 'smiley'));
    });
    ready(Boolean(gpu));
    if (!gpu) return;
    painters.set(root, gpu);
    paintSmileySphere(root, snapshots.get(root) ?? resolvePose('neutral', 'smiley'));
  };
  const lost = (event: Event) => {
    event.preventDefault();
    stop();
  };
  canvas.addEventListener('webglcontextlost', lost);
  canvas.addEventListener('webglcontextrestored', start);
  const visibility =
    typeof MutationObserver === 'undefined'
      ? null
      : new MutationObserver(() => {
          if (active)
            paintSmileySphere(root, snapshots.get(root) ?? resolvePose('neutral', 'smiley'));
        });
  visibility?.observe(root, { attributes: true, attributeFilter: ['data-rig-visible'] });
  ready(false);
  start();
  return () => {
    if (!active) return;
    active = false;
    visibility?.disconnect();
    canvas.removeEventListener('webglcontextlost', lost);
    canvas.removeEventListener('webglcontextrestored', start);
    stop();
    releaseNativeContext(context);
  };
}

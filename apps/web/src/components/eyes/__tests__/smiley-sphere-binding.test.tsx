import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { SmileySphere } from '../smiley/SmileySphere';
import { bindSmileySphere, paintSmileySphere } from '../smiley/sphere-binding';
import { restChannelValues } from '../rig/channels';
import { sphereGraphics } from './sphere-graphics';
import * as binding from '../smiley/sphere-binding';
import { smileyClothGraphics } from './smiley-cloth-graphics';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function host() {
  const root = document.createElement('span');
  const body = document.createElement('span');
  const canvas = document.createElement('canvas');
  root.className = 'lia-smiley';
  body.append(canvas);
  root.append(body);
  return { root, body, canvas };
}

describe('Sphere context belongs to the native rig, with a fixed-image fallback', () => {
  it('releases its native context only after unmount disposal and removing restoration listeners', async () => {
    const { root, canvas } = host(),
      gl = smileyClothGraphics(),
      loseContext = vi.fn();
    vi.stubGlobal('WebGLRenderingContext', class {});
    gl.getExtension.mockReturnValue({ loseContext });
    vi.spyOn(canvas, 'getContext').mockReturnValue(gl as never);
    const dispose = bindSmileySphere(canvas, root);
    root.dataset.rigVisible = 'false';
    await Promise.resolve();
    expect(loseContext).not.toHaveBeenCalled();
    dispose();
    dispose();
    expect(loseContext).toHaveBeenCalledTimes(1);
    expect(gl.deleteProgram.mock.invocationCallOrder.at(-1)).toBeLessThan(
      loseContext.mock.invocationCallOrder[0]
    );
    const allocations = gl.createProgram.mock.calls.length;
    canvas.dispatchEvent(new Event('webglcontextrestored'));
    expect(gl.createProgram).toHaveBeenCalledTimes(allocations);
  });
  it('paints the current native pose, falls back on context loss and restores once without a retry clock', () => {
    const { root, body, canvas } = host();
    const gl = sphereGraphics();
    paintSmileySphere(root, { ...restChannelValues(), headYaw: 0.8 });
    const dispose = bindSmileySphere(canvas, root, gl);
    expect(body.dataset.sphereReady).toBe('true');
    expect(gl.drawArrays).toHaveBeenCalledTimes(1);
    const loss = new Event('webglcontextlost', { cancelable: true });
    canvas.dispatchEvent(loss);
    expect(loss.defaultPrevented).toBe(true);
    expect(body.dataset.sphereReady).toBe('false');
    paintSmileySphere(root, { ...restChannelValues(), headYaw: -0.8 });
    expect(gl.drawArrays).toHaveBeenCalledTimes(1);
    canvas.dispatchEvent(new Event('webglcontextrestored'));
    expect(gl.drawArrays).toHaveBeenCalledTimes(2);
    expect(body.dataset.sphereReady).toBe('true');
    dispose();
    dispose();
    canvas.dispatchEvent(new Event('webglcontextrestored'));
    paintSmileySphere(root, restChannelValues());
    expect(gl.drawArrays).toHaveBeenCalledTimes(2);
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(2);
  });

  it('keeps the fixed original sphere on an unavailable or failed context without repeatedly allocating', () => {
    const { root, body, canvas } = host();
    bindSmileySphere(canvas, root, null)();
    expect(body.dataset.sphereReady).toBe('false');
    const gl = sphereGraphics();
    gl.getProgramParameter.mockReturnValue(false);
    const dispose = bindSmileySphere(canvas, root, gl);
    for (let index = 0; index < 5; index++) paintSmileySphere(root, restChannelValues());
    expect(body.dataset.sphereReady).toBe('false');
    expect(gl.createProgram).toHaveBeenCalledTimes(1);
    dispose();
  });

  it('retains the cloth fallback when the native sphere cannot provide fragment depth', () => {
    const { root, canvas } = host();
    const dispose = bindSmileySphere(canvas, root, sphereGraphics());
    paintSmileySphere(root, { ...restChannelValues(), weatherCold: 0.65 });
    expect(root.dataset.volumeScarfReady).toBe('false');
    dispose();
    expect(root.dataset.volumeScarfReady).toBe('false');
  });

  it('marks real cloth ready only after upload and clears it on native hiding and context loss', async () => {
    const images: { src: string; onload: (() => void) | null; onerror: (() => void) | null }[] = [];
    vi.stubGlobal(
      'Image',
      class {
        src = '';
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;
        constructor() {
          images.push(this);
        }
      }
    );
    const { root, body, canvas } = host();
    root.dataset.rigVisible = 'true';
    const gl = smileyClothGraphics();
    paintSmileySphere(root, { ...restChannelValues(), weatherCold: 0.65 });
    const dispose = bindSmileySphere(canvas, root, gl);
    expect(root.dataset.volumeScarfReady).toBe('false');
    expect(images[0]?.src).toBe('/avatars/scarf/v1/front.webp');
    images[0]?.onload?.();
    expect(root.dataset.volumeScarfReady).toBe('true');
    root.dataset.rigVisible = 'false';
    await Promise.resolve();
    expect(root.dataset.volumeScarfReady).toBe('false');
    expect(gl.deleteTexture).toHaveBeenCalledTimes(1);
    root.dataset.rigVisible = 'true';
    await Promise.resolve();
    expect(root.dataset.volumeScarfReady).toBe('false');
    canvas.dispatchEvent(new Event('webglcontextlost', { cancelable: true }));
    expect(body.dataset.sphereReady).toBe('false');
    expect(images.at(-1)?.onload).toBeNull();
    expect(root.dataset.volumeScarfReady).toBe('false');
    dispose();
    expect(gl.deleteTexture).toHaveBeenCalledTimes(gl.createTexture.mock.calls.length);
  });

  it('rebuilds only the sized canvas on sm/md/lg changes and repaints a static native pose without remounting the host', () => {
    const gl = sphereGraphics();
    const bind = binding.bindSmileySphere;
    vi.spyOn(binding, 'bindSmileySphere').mockImplementation((canvas, root) =>
      bind(canvas, root, gl)
    );
    const view = render(
      <span className="lia-smiley">
        <SmileySphere size="sm" />
      </span>
    );
    const first = view.container.querySelector('canvas');
    const root = view.container.firstElementChild!;
    expect(first?.width).toBe(52);
    view.rerender(
      <span className="lia-smiley">
        <SmileySphere size="md" />
      </span>
    );
    expect(view.container.firstElementChild).toBe(root);
    expect(view.container.querySelector('canvas')).not.toBe(first);
    expect(view.container.querySelector('canvas')?.width).toBe(78);
    view.rerender(
      <span className="lia-smiley">
        <SmileySphere size="lg" />
      </span>
    );
    expect(view.container.querySelector('canvas')?.width).toBe(115);
    expect(gl.viewport.mock.calls).toEqual([
      [0, 0, 52, 52],
      [0, 0, 78, 78],
      [0, 0, 115, 115],
    ]);
    expect(gl.drawArrays).toHaveBeenCalledTimes(3);
    view.unmount();
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(3);
  });
});

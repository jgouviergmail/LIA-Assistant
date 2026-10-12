import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  bindBodyVolume,
  paintBodyVolume,
  setBodyVolumeVisibility,
  setBodyVolumeReducedMotion,
} from '../volume-binding';
import * as masks from '../volume-mask';
import * as fringe from '../volume-fringe';
import { restChannelValues } from '../../rig/channels';
import { smileyClothGraphics } from '../../__tests__/smiley-cloth-graphics';
import { createVolumeSurfaceWriter } from '../volume-writer';

class BodyImage {
  static instances: BodyImage[] = [];
  src = '';
  complete = false;
  naturalWidth = 192;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    BodyImage.instances.push(this);
  }
  load() {
    this.complete = true;
    this.onload?.();
  }
}
afterEach(() => {
  BodyImage.instances = [];
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function host(visible = true) {
  const root = document.createElement('span'),
    canvas = document.createElement('canvas');
  root.dataset.rigVisible = String(visible);
  canvas.width = canvas.height = 192;
  root.append(canvas);
  vi.stubGlobal('Image', BodyImage);
  const alpha = new Uint8Array(192 * 192);
  for (let y = 10; y < 182; y++) for (let x = 28; x < 164; x++) alpha[y * 192 + x] = 255;
  vi.spyOn(masks, 'readVolumeMask').mockReturnValue({ width: 192, height: 192, alpha });
  vi.spyOn(fringe, 'volumeFringeMask').mockReturnValue(null);
  return { root, canvas };
}
describe('the rig alone owns volume visibility, playback and bounded resources', () => {
  it('uploads the supplied fringe mask once per GPU lifetime and releases both textures', () => {
    const { root, canvas } = host();
    const gl = smileyClothGraphics();
    const fringeMask = document.createElement('canvas');
    fringeMask.width = fringeMask.height = 192;
    vi.mocked(fringe.volumeFringeMask).mockReturnValue(fringeMask);
    const dispose = bindBodyVolume(canvas, root, 'spirit', 'female', gl);
    expect(fringe.volumeFringeMask).not.toHaveBeenCalled();
    BodyImage.instances[0].load();
    expect(fringe.volumeFringeMask).toHaveBeenCalledOnce();
    expect(gl.createTexture).toHaveBeenCalledTimes(2);
    expect(gl.texImage2D.mock.calls.filter(call => call.at(-1) === fringeMask)).toHaveLength(1);
    paintBodyVolume(root, { ...restChannelValues(), headYaw: 1 });
    expect(fringe.volumeFringeMask).toHaveBeenCalledOnce();
    expect(gl.texImage2D).toHaveBeenCalledTimes(2);
    setBodyVolumeVisibility(root, false);
    expect(gl.deleteTexture).toHaveBeenCalledTimes(2);
    setBodyVolumeVisibility(root, true);
    expect(fringe.volumeFringeMask).toHaveBeenCalledOnce();
    expect(gl.texImage2D.mock.calls.filter(call => call.at(-1) === fringeMask)).toHaveLength(2);
    dispose();
    dispose();
    expect(gl.deleteTexture).toHaveBeenCalledTimes(4);
    expect(gl.deleteTexture).toHaveBeenCalledTimes(gl.createTexture.mock.calls.length);
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(gl.createBuffer.mock.calls.length);
    expect(gl.deleteProgram).toHaveBeenCalledTimes(gl.createProgram.mock.calls.length);
  });
  it('confines the live organs with the loaded material contour, caches a stationary head and clears every projection on fallback', () => {
    const { root, canvas } = host(),
      gl = smileyClothGraphics();
    root.dataset.style = 'billes';
    root.dataset.volumeCharacter = 'spirit';
    root.dataset.volumeVariant = 'female';
    root.style.setProperty('--companion-eye-y', '52.405%');
    root.style.setProperty('--avatar-crown-y', '0%');
    root.style.setProperty('--avatar-face-y', '52.405%');
    const eye = document.createElement('span');
    eye.dataset.volumeSurface = 'left';
    root.append(eye);
    const writer = createVolumeSurfaceWriter(root),
      dispose = bindBodyVolume(canvas, root, 'spirit', 'female', gl),
      rest = restChannelValues();
    writer.write(rest);
    expect(root.style.getPropertyValue('--volume-face-clip')).toBe('');
    BodyImage.instances[0].load();
    const initial = root.style.getPropertyValue('--volume-face-clip');
    expect(initial).toMatch(/^polygon\(/);
    const coordinates = initial.match(/[-\d.]+(?=%)/g)!.map(Number);
    expect(coordinates).toHaveLength(128);
    expect(coordinates.every(Number.isFinite)).toBe(true);
    expect(Math.max(...coordinates) - Math.min(...coordinates)).toBeGreaterThan(30);
    writer.write({ ...rest, headYaw: 1, headPitch: -0.6 });
    const turned = root.style.getPropertyValue('--volume-face-clip');
    expect(turned).not.toBe(initial);
    const changes = vi.spyOn(root.style, 'setProperty');
    writer.write({ ...rest, headYaw: 1, headPitch: -0.6, gazeX: 1, mouthOpen: 0.5 });
    expect(root.style.getPropertyValue('--volume-face-clip')).toBe(turned);
    expect(changes.mock.calls.some(([property]) => property === '--volume-face-clip')).toBe(false);
    setBodyVolumeVisibility(root, false);
    expect(root.style.getPropertyValue('--volume-face-clip')).toBe('');
    expect(root.style.getPropertyValue('--volume-crown-transform')).toBe('');
    expect(eye.style.transform).toBe('');
    setBodyVolumeVisibility(root, true);
    expect(root.style.getPropertyValue('--volume-face-clip')).toBe(turned);
    dispose();
    expect(root.style.getPropertyValue('--volume-face-clip')).toBe('');
    writer.dispose();
  });
  it('allocates nothing while hidden or reduced, reads alpha once, caches mouth-only frames and releases every GPU object', () => {
    const { root, canvas } = host(false),
      gl = smileyClothGraphics(),
      raf = vi.spyOn(window, 'requestAnimationFrame');
    const dispose = bindBodyVolume(canvas, root, 'oscar', 'female', gl);
    expect(BodyImage.instances).toHaveLength(0);
    setBodyVolumeReducedMotion(root, true);
    setBodyVolumeVisibility(root, true);
    expect(gl.createProgram).not.toHaveBeenCalled();
    expect(BodyImage.instances).toHaveLength(0);
    setBodyVolumeReducedMotion(root, false);
    expect(BodyImage.instances[0].src).toContain('/oscar/');
    expect(gl.createProgram).not.toHaveBeenCalled();
    BodyImage.instances[0].load();
    expect(root.dataset.volumeReady).toBe('true');
    expect(gl.drawElements).toHaveBeenCalledTimes(1);
    const rest = restChannelValues();
    paintBodyVolume(root, rest);
    paintBodyVolume(root, { ...rest, mouthOpen: 0.6 });
    expect(gl.drawElements).toHaveBeenCalledTimes(1);
    paintBodyVolume(root, { ...rest, headYaw: 0.7 });
    expect(gl.drawElements).toHaveBeenCalledTimes(2);
    setBodyVolumeVisibility(root, false);
    expect(root.dataset.volumeReady).toBe('false');
    setBodyVolumeVisibility(root, true);
    expect(root.dataset.volumeReady).toBe('true');
    expect(masks.readVolumeMask).toHaveBeenCalledTimes(1);
    expect(BodyImage.instances).toHaveLength(1);
    expect(raf).not.toHaveBeenCalled();
    dispose();
    dispose();
    expect(gl.deleteTexture).toHaveBeenCalledTimes(gl.createTexture.mock.calls.length);
    expect(gl.deleteBuffer).toHaveBeenCalledTimes(gl.createBuffer.mock.calls.length);
    expect(gl.deleteProgram).toHaveBeenCalledTimes(gl.createProgram.mock.calls.length);
  });
  it('keeps the baked body on an unavailable alpha reader or failed link without a retry clock', () => {
    const { root, canvas } = host(),
      gl = smileyClothGraphics();
    vi.mocked(masks.readVolumeMask).mockReturnValue(null);
    const dispose = bindBodyVolume(canvas, root, 'moss', 'male', gl);
    BodyImage.instances[0].load();
    for (let i = 0; i < 8; i++) {
      setBodyVolumeVisibility(root, false);
      setBodyVolumeVisibility(root, true);
      paintBodyVolume(root, restChannelValues());
    }
    expect(gl.createProgram).not.toHaveBeenCalled();
    expect(root.dataset.volumeReady).toBe('false');
    expect(BodyImage.instances).toHaveLength(1);
    dispose();
  });
  it('reconstructs from the latest native snapshot after context loss and cancels late material callbacks on disposal', () => {
    const { root, canvas } = host(),
      gl = smileyClothGraphics();
    const dispose = bindBodyVolume(canvas, root, 'orbit', 'male', gl);
    BodyImage.instances[0].load();
    const loss = new Event('webglcontextlost', { cancelable: true });
    canvas.dispatchEvent(loss);
    expect(loss.defaultPrevented).toBe(true);
    expect(root.dataset.volumeReady).toBe('false');
    paintBodyVolume(root, { ...restChannelValues(), headYaw: -1 });
    canvas.dispatchEvent(new Event('webglcontextrestored'));
    expect(root.dataset.volumeReady).toBe('true');
    expect(gl.drawElements).toHaveBeenCalledTimes(2);
    dispose();
    expect(BodyImage.instances[0].onload).toBeNull();
    canvas.dispatchEvent(new Event('webglcontextrestored'));
    expect(gl.drawElements).toHaveBeenCalledTimes(2);
  });
});

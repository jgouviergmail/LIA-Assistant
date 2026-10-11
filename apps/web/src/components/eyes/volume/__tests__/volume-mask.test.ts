import { afterEach, describe, expect, it, vi } from 'vitest';
import { readVolumeMask } from '../volume-mask';

const original = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, 'getContext')!;
afterEach(() => Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', original));

describe('one bounded material alpha read', () => {
  it('reads exactly the RGBA alpha channel at the fixed source resolution', () => {
    const rgba = new Uint8ClampedArray(192 * 192 * 4);
    rgba.set([255, 30, 5, 0, 0, 255, 40, 180, 1, 2, 255, 255]);
    rgba[rgba.length - 1] = 73;
    const context: Pick<CanvasRenderingContext2D, 'drawImage' | 'getImageData'> = {
      drawImage: vi.fn(),
      getImageData: vi.fn<CanvasRenderingContext2D['getImageData']>(() => ({
        data: rgba,
        width: 192,
        height: 192,
        colorSpace: 'srgb',
      })),
    };
    const getContext = vi.fn(() => context);
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
      value: getContext,
      configurable: true,
    });
    const image = document.createElement('img'),
      mask = readVolumeMask(image);
    expect(mask?.width).toBe(192);
    expect(mask?.height).toBe(192);
    expect(mask?.alpha).toHaveLength(192 * 192);
    expect([...mask!.alpha.slice(0, 3)]).toEqual([0, 180, 255]);
    expect(mask!.alpha.at(-1)).toBe(73);
    expect(getContext).toHaveBeenCalledExactlyOnceWith('2d', { willReadFrequently: true });
    expect(context.drawImage).toHaveBeenCalledExactlyOnceWith(image, 0, 0, 192, 192);
    expect(context.getImageData).toHaveBeenCalledExactlyOnceWith(0, 0, 192, 192);
  });
  it('leaves the baked fallback available if Canvas2D is absent or the read is rejected', () => {
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
      value: () => null,
      configurable: true,
    });
    expect(readVolumeMask(document.createElement('img'))).toBeNull();
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
      value: () => {
        throw new DOMException('Read rejected', 'SecurityError');
      },
      configurable: true,
    });
    expect(readVolumeMask(document.createElement('img'))).toBeNull();
  });
});

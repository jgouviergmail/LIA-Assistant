import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { afterEach, expect, it, vi } from 'vitest';
import { nightStrength, shadeSprite } from '../art/lighting';
import type { Sprite } from '../art/painter';

afterEach(() => vi.restoreAllMocks());

function sprite(): Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = 160;
  canvas.height = 100;
  return { canvas, width: 80, height: 50, anchorX: 40, anchorY: 25 };
}

it('keeps dawn and dusk lighter than night, and an unknown civil clock neutral', () => {
  expect(nightStrength('unknown')).toBe(0);
  expect(nightStrength('dawn')).toBeGreaterThan(0);
  expect(nightStrength('dawn')).toBeLessThan(nightStrength('evening'));
  expect(nightStrength('evening')).toBeLessThan(nightStrength('night'));
  expect(nightStrength('night')).toBeLessThan(1);
});

it('does no canvas work in neutral daylight, including after context loss', () => {
  const asset = sprite();
  const getContext = vi.spyOn(asset.canvas, 'getContext').mockReturnValue(null);
  expect(shadeSprite(asset, 0)).toBe(asset);
  expect(getContext).not.toHaveBeenCalled();
  expect(() => shadeSprite(asset, nightStrength('night'))).toThrow('Canvas unavailable');
});

it('shades the full physical texture without changing its logical placement or leaking canvas state', () => {
  const asset = sprite();
  const snapshot = { ...asset };
  const context = canvasContext({
    save: vi.fn(),
    restore: vi.fn(),
    setTransform: vi.fn(),
    globalCompositeOperation: 'source-over' as GlobalCompositeOperation,
    fillStyle: '',
    fillRect: vi.fn(),
  });
  const fill = { operation: '', rectangle: [] as number[] };
  context.fillRect.mockImplementation((...bounds: number[]) => {
    fill.operation = context.globalCompositeOperation;
    fill.rectangle = bounds;
  });
  context.restore.mockImplementation(() => {
    context.globalCompositeOperation = 'source-over';
  });
  vi.spyOn(asset.canvas, 'getContext').mockReturnValue(context);
  expect(shadeSprite(asset, nightStrength('night'))).toBe(asset);
  expect(asset).toEqual(snapshot);
  expect(fill).toEqual({ operation: 'source-atop', rectangle: [0, 0, 160, 100] });
  expect(context.setTransform).toHaveBeenCalledWith(1, 0, 0, 1, 0, 0);
  expect(context.save).toHaveBeenCalledOnce();
  expect(context.restore).toHaveBeenCalledOnce();
  expect(context.globalCompositeOperation).toBe('source-over');
});

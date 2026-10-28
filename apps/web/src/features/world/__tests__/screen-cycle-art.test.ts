import { afterEach, expect, it, vi } from 'vitest';
import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { WORLD } from '../definition';
import { paintProp } from '../art/props';
import type { ScreenVariant } from '../decor-presentation';
afterEach(() => vi.restoreAllMocks());
it.each(['display', 'desk'] as const)(
  'returns %s to exactly its initial authored drawing after cycling five variants',
  kind => {
    const prop = WORLD.props.find(item => item.kind === kind && item.tone !== 'sage');
    if (!prop) throw new Error('Missing screen');
    const moveTo = vi.fn(),
      context = canvasContext({ moveTo });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context);
    const draw = (variant?: ScreenVariant) => {
      moveTo.mockClear();
      paintProp(prop, 1, false, 'neutral', 0, variant === undefined ? {} : { screen: variant });
      return JSON.stringify(moveTo.mock.calls);
    };
    const initial = draw();
    const variants: ScreenVariant[] = [1, 2, 3, 4, 0];
    const drawings = variants.map(draw);
    expect(drawings[4]).toBe(initial);
    expect(new Set(drawings).size).toBe(5);
  }
);

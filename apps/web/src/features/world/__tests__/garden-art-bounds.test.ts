import { canvasContext } from '@/__tests__/fixtures/canvas-context';
import { afterEach, expect, it, vi } from 'vitest';
import { WORLD } from '../definition';
import { paintProp } from '../art/props';

/** Geometric cache contract. Browser pixel tests separately inspect antialiasing and silhouettes. */
function boundsContext() {
  const points: number[][] = [];
  let scale = 1,
    tx = 0,
    ty = 0;
  const stack: number[][] = [];
  const point = (x: number, y: number) => points.push([x * scale + tx, y * scale + ty]);
  const c = canvasContext({
    scale: (x: number) => {
      scale *= x;
    },
    translate: (x: number, y: number) => {
      tx += x * scale;
      ty += y * scale;
    },
    save: () => stack.push([scale, tx, ty]),
    restore: () => {
      [scale, tx, ty] = stack.pop()!;
    },
    beginPath: vi.fn(),
    closePath: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    clip: vi.fn(),
    fillRect: (x: number, y: number, w: number, h: number) => {
      point(x, y);
      point(x + w, y + h);
    },
    moveTo: point,
    lineTo: point,
    quadraticCurveTo: (cx: number, cy: number, x: number, y: number) => {
      point(cx, cy);
      point(x, y);
    },
    ellipse: (x: number, y: number, rx: number, ry: number) => {
      expect(rx).toBeGreaterThanOrEqual(0);
      expect(ry).toBeGreaterThanOrEqual(0);
      point(x - rx, y - ry);
      point(x + rx, y + ry);
    },
    createLinearGradient: () => ({ addColorStop: vi.fn() }),
  });
  return { c: c, points, depth: () => stack.length };
}
afterEach(() => vi.restoreAllMocks());

it.each([1, 1.25, 1.75])(
  'fits every authored tree and the pond within its finite cached surface at ratio %s',
  ratio => {
    for (const prop of WORLD.props.filter(p => p.kind === 'tree' || p.kind === 'pond')) {
      const { c, points, depth } = boundsContext();
      vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(c);
      const texture = paintProp(prop, ratio, false);
      expect(points.length, prop.id).toBeGreaterThan(20);
      expect(depth(), prop.id).toBe(0);
      expect(texture.canvas.width * texture.canvas.height * 4, prop.id).toBeLessThan(
        4 * 1024 * 1024
      );
      for (const [x, y] of points) {
        expect(Number.isFinite(x + y), prop.id).toBe(true);
        expect(x, prop.id).toBeGreaterThan(0);
        expect(x, prop.id).toBeLessThan(texture.canvas.width);
        expect(y, prop.id).toBeGreaterThan(0);
        expect(y, prop.id).toBeLessThan(texture.canvas.height);
      }
      texture.canvas.width = 0;
      vi.restoreAllMocks();
    }
  }
);

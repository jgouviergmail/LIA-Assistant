import { describe, expect, it } from 'vitest';
import { volumeFringeAlpha } from '../volume-coverage';
import { withSoftFringe } from '../volume-fringe';
import { volumeProfile, type VolumeMask, type VolumeMesh } from '../volume-geometry';

const WIDTH = 12;
type Face = 'front' | 'back';
type Rectangle = readonly [number, number, number, number];

function mask(value = 255): VolumeMask {
  return { width: WIDTH, height: WIDTH, alpha: new Uint8Array(WIDTH * WIDTH).fill(value) };
}

/** Actual indexed triangles in UV space. The square frame deliberately leaves
 * a two-pixel hole; an unrelated rear surface must never fill it for the film. */
function frameMesh(): VolumeMesh {
  const vertices: number[] = [];
  const indices: number[] = [];
  const quad = ([left, top, right, bottom]: Rectangle, face: Face) => {
    const first = vertices.length / 8;
    for (const [u, v] of [
      [left, top],
      [right, top],
      [right, bottom],
      [left, bottom],
    ])
      vertices.push(
        (u - 0.5) * 2.6,
        (v - 0.5) * 2.6,
        face === 'front' ? 0.2 : -0.2,
        0,
        0,
        face === 'front' ? 1 : -1,
        u,
        v
      );
    indices.push(first, first + 1, first + 2, first, first + 2, first + 3);
  };
  quad([3 / WIDTH, 3 / WIDTH, 5 / WIDTH, 9 / WIDTH], 'front');
  quad([7 / WIDTH, 3 / WIDTH, 9 / WIDTH, 9 / WIDTH], 'front');
  quad([5 / WIDTH, 3 / WIDTH, 7 / WIDTH, 5 / WIDTH], 'front');
  quad([5 / WIDTH, 7 / WIDTH, 7 / WIDTH, 9 / WIDTH], 'front');
  quad([0, 0, 1, 1], 'back');
  return { vertices: new Float32Array(vertices), indices: new Uint16Array(indices) };
}

function inFrame(x: number, y: number): boolean {
  const square = x >= 3 && x < 9 && y >= 3 && y < 9;
  const hole = x >= 5 && x < 7 && y >= 5 && y < 7;
  return square && !hole;
}

describe('the film keeps only the source alpha absent from physical front coverage', () => {
  it('removes opaque pixels on the indexed front frame, retaining its hole and uncovered border', () => {
    const source = mask();
    const before = source.alpha.slice();
    const result = volumeFringeAlpha(frameMesh(), source);
    expect(result).toHaveLength(WIDTH * WIDTH);
    for (let y = 0; y < WIDTH; y++)
      for (let x = 0; x < WIDTH; x++) expect(result[y * WIDTH + x]).toBe(inFrame(x, y) ? 0 : 255);
    expect(source.alpha).toEqual(before);
  });

  it('preserves every soft source alpha and uncovered opaque detail at the threshold', () => {
    const source = mask();
    source.alpha[4 * WIDTH + 4] = 179;
    source.alpha[4 * WIDTH + 3] = 96;
    source.alpha[3 * WIDTH + 4] = 1;
    source.alpha[3 * WIDTH + 3] = 0;
    source.alpha[8 * WIDTH + 8] = 180;
    source.alpha[8 * WIDTH + 7] = 181;
    source.alpha[1 * WIDTH + 1] = 180;
    const before = source.alpha.slice();
    const result = volumeFringeAlpha(frameMesh(), source);
    for (let y = 0; y < WIDTH; y++)
      for (let x = 0; x < WIDTH; x++) {
        const index = y * WIDTH + x;
        const expected = inFrame(x, y) && before[index] >= 180 ? 0 : before[index];
        expect(result[index]).toBe(expected);
      }
    expect(result[6 * WIDTH + 6]).toBe(255);
    expect(source.alpha).toEqual(before);
  });

  it('does not use the full planar fringe itself as physical coverage', () => {
    const source = mask();
    const mesh = withSoftFringe(frameMesh(), volumeProfile('spirit', 'female'));
    const result = volumeFringeAlpha(mesh, source);
    expect(result[1 * WIDTH + 1]).toBe(255);
    expect(result[6 * WIDTH + 6]).toBe(255);
    expect(result[4 * WIDTH + 4]).toBe(0);
  });

  it('retains the complete source when no physical front triangle covers it', () => {
    const source = mask();
    source.alpha[0] = 0;
    source.alpha[17] = 42;
    const all = frameMesh();
    const back = { vertices: all.vertices, indices: all.indices.slice(-6) };
    expect(volumeFringeAlpha(back, source)).toEqual(source.alpha);
    expect(
      volumeFringeAlpha({ vertices: new Float32Array(), indices: new Uint16Array() }, source)
    ).toEqual(source.alpha);
  });

  it.each(['descending', 'ascending'] as const)(
    'covers opaque pixels on the shared %s diagonal without opening a seam',
    diagonal => {
      const vertices = new Float32Array([
        -1.3, -1.3, 0.2, 0, 0, 1, 0, 0, 1.3, -1.3, 0.2, 0, 0, 1, 1, 0, 1.3, 1.3, 0.2, 0, 0, 1, 1, 1,
        -1.3, 1.3, 0.2, 0, 0, 1, 0, 1,
      ]);
      const indices = new Uint16Array(
        diagonal === 'descending' ? [0, 1, 2, 0, 2, 3] : [0, 1, 3, 1, 2, 3]
      );
      const result = volumeFringeAlpha({ vertices, indices }, mask());
      expect([...result].every(alpha => alpha === 0)).toBe(true);
    }
  );
});

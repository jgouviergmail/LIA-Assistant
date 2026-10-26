import { describe, expect, it } from 'vitest';
import { WORLD } from '../definition';
import { propStyleVariant, propTextureKey, groundVariant, floorVariant } from '../art/prop-style';

describe('authored art texture ownership', () => {
  const tree = WORLD.props.find(p => p.kind === 'tree');
  if (!tree) throw new Error('Missing representative tree');
  it('varies a garden deterministically without creating one texture per coordinate', () => {
    const variants = Array.from({ length: 100 }, (_, x) =>
      propStyleVariant({ ...tree, x, y: x * 3 })
    );
    expect(new Set(variants).size).toBe(3);
    expect(variants.every(v => Number.isInteger(v) && v >= 0 && v < 3)).toBe(true);
    expect(variants).toEqual(
      Array.from({ length: 100 }, (_, x) => propStyleVariant({ ...tree, x, y: x * 3 }))
    );
    const keys = new Set(
      Array.from({ length: 100 }, (_, x) =>
        propTextureKey({ ...tree, id: String(x), x, y: x * 3 }, false, false)
      )
    );
    expect(keys.size).toBe(3);
  });
  it('keeps the foreground mask and matching colour art in the same style family', () => {
    const prop = { ...tree, x: 13, y: 22 };
    expect(propTextureKey(prop, false, false)).not.toBe(propTextureKey(prop, false, true));
    expect(propTextureKey(prop, false, false)).not.toBe(propTextureKey(prop, true, false));
    expect(propTextureKey(prop, false, false)).toBe(
      propTextureKey({ ...prop, id: 'another-public-label' }, false, false)
    );
  });
  it('never shares private palette textures with another appearance', () => {
    const prop = tree;
    expect(propTextureKey(prop, true, false)).not.toBe(
      propTextureKey({ ...prop, tone: 'clay' }, true, false)
    );
  });
  it('shares non-varied materials across coordinates while preserving different shapes', () => {
    const wall = WORLD.props.find(prop => prop.kind === 'partition');
    if (!wall) throw new Error('Missing authored wall');
    expect(propStyleVariant(wall)).toBe(0);
    expect(propTextureKey(wall, false, false)).toBe(
      propTextureKey({ ...wall, x: 42, y: 3 }, false, false)
    );
    expect(propTextureKey(wall, false, false)).not.toBe(
      propTextureKey({ ...wall, width: 2 }, false, false)
    );
  });
  it('breaks diagonal floor repetition while retaining a small bounded atlas', () => {
    const variants = Array.from({ length: 64 }, (_, i) => groundVariant(i % 8, Math.floor(i / 8)));
    expect(new Set(variants).size).toBe(8);
    expect(variants.every(v => Number.isInteger(v) && v >= 0 && v < 8)).toBe(true);
    expect(Array.from({ length: 8 }, (_, x) => groundVariant(x, 0))).not.toEqual(
      Array.from({ length: 8 }, (_, x) => groundVariant(x, 4))
    );
  });
});

it('does not reuse a chair image or foreground mask for a different orientation', () => {
  const chair = WORLD.props.find(prop => prop.kind === 'chair');
  if (!chair) throw new Error('Missing chair');
  for (const mask of [false, true]) {
    expect(propTextureKey({ ...chair, facing: 0 }, false, mask)).not.toBe(
      propTextureKey({ ...chair, facing: 3 }, false, mask)
    );
  }
});

it('keeps architectural materials distinct in both art and foreground caches', () => {
  const wall = WORLD.props.find(prop => prop.kind === 'partition');
  if (!wall) throw new Error('Missing wall');
  for (const mask of [false, true]) {
    const glass = { ...wall, wallFinish: 'glass' as const };
    const brick = { ...wall, wallFinish: 'brick' as const };
    expect(propTextureKey(glass, false, mask)).not.toBe(propTextureKey(brick, false, mask));
    expect(propTextureKey(glass, false, mask)).toBe(
      propTextureKey({ ...glass, x: 100, y: 100, id: 'same-material-elsewhere' }, false, mask)
    );
  }
});

it('separates glazed wall images from solid spans and keeps checker seams continuous', () => {
  const wall = WORLD.props.find(prop => prop.kind === 'partition');
  if (!wall) throw new Error('Missing wall');
  expect(propTextureKey({ ...wall, wallWindow: true }, false, false)).not.toBe(
    propTextureKey({ ...wall, wallWindow: false }, false, false)
  );
  expect(floorVariant('grass', 7, 16)).toBe(groundVariant(7, 16));
  expect([14, 15, 16, 17].map(x => floorVariant('checker', x, 8))).toEqual([1, 1, 0, 0]);
  expect(floorVariant('checker', 16, 9)).toBe(floorVariant('checker', 17, 8));
});

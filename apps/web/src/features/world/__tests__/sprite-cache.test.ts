import { expect, it, vi } from 'vitest';
import { SpriteCache } from '../art/sprite-cache';
import type { Sprite } from '../art/painter';
function sprite(width = 8): Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = width; canvas.height = 8;
  return { canvas, width, height: 8, anchorX: 4, anchorY: 8 };
}
it('bounds retained actor art by bytes and recency, then releases all owned surfaces', () => {
  const pool = new SpriteCache(512, 3);
  const first = sprite(), second = sprite(), third = sprite();
  expect(pool.get('one', () => first)).toBe(first);
  pool.get('two', () => second);
  const unused = vi.fn(() => sprite());
  expect(pool.get('one', unused)).toBe(first);
  expect(unused).not.toHaveBeenCalled();
  pool.get('three', () => third);
  expect(second.canvas.width).toBe(0);
  expect(first.canvas.width).toBe(8);
  expect(pool.bytes).toBe(512);
  pool.clear();
  expect(first.canvas.width).toBe(0);
  expect(third.canvas.width).toBe(0);
  expect(pool.bytes).toBe(0);
  pool.clear();
});
it('rejects an oversized allocation without retaining an unowned surface', () => {
  const pool = new SpriteCache(100, 1);
  const value = sprite(100);
  expect(() => pool.get('oversized', () => value)).toThrow('world_actor_texture_limit');
  expect(pool.bytes).toBe(0);
  expect(value.canvas.width).toBe(0);
});

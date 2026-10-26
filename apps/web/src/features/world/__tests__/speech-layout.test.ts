import { expect, it } from 'vitest';
import { speechBox, speechLines } from '../art/speech';
const context = { measureText: (text: string) => ({ width: Array.from(text).length * 8 }) };
it('keeps long CJK/emoji speech within four lines without splitting surrogate pairs', () => {
  const lines = speechLines(context, '你好 🌿'.repeat(200), 120);
  expect(lines.length).toBeLessThanOrEqual(4);
  expect(lines.at(-1)?.endsWith('…')).toBe(true);
  for (const line of lines) {
    expect(context.measureText(line).width).toBeLessThanOrEqual(120);
    expect(line).not.toMatch(/[\uD800-\uDFFF]/u);
  }
});
it('preserves explicit paragraphs, literal markup and readable word boundaries', () => {
  const lines = speechLines(context, 'Hello world\n<img src=x>', 160);
  expect(lines).toEqual(['Hello world', '<img src=x>']);
});

it('keeps simultaneous bubbles separated and inside a narrow viewport', () => {
  const size = { width: 320, height: 740 },
    anchor = { x: 5, y: 400 };
  const first = speechBox(anchor, 260, 80, size, []);
  expect(first).not.toBeNull();
  if (!first) throw new Error('Missing first bubble');
  const second = speechBox(anchor, 260, 80, size, [first]);
  expect(second).not.toBeNull();
  if (!second) throw new Error('Missing second bubble');
  expect(second.y + second.height + 8).toBeLessThanOrEqual(first.y);
  expect(first.x).toBeGreaterThanOrEqual(8);
  expect(first.x + first.width).toBeLessThanOrEqual(312);
  expect(
    speechBox({ x: 160, y: 50 }, 260, 100, size, [{ x: 8, y: 8, width: 300, height: 200 }])
  ).toBeNull();
});

it('bounds speech at the viewport bottom and omits a box that cannot fit', () => {
  const box = speechBox({ x: 300, y: 800 }, 260, 80, { width: 320, height: 740 }, []);
  expect(box && box.y + box.height).toBeLessThanOrEqual(732);
  expect(speechBox({ x: 10, y: 10 }, 100, 120, { width: 320, height: 100 }, [])).toBeNull();
});

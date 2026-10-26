import { expect, it } from 'vitest';
import { WORLD, groundAt } from '../definition';
import { compileNavigation, findRoute } from '../navigation';

const rooms = WORLD.zones.filter(z => z.covered && z.id !== 'home');
const bounds = {
  x: Math.min(...rooms.map(z => z.x)),
  y: Math.min(...rooms.map(z => z.y)),
  right: Math.max(...rooms.map(z => z.x + z.width)),
  bottom: Math.max(...rooms.map(z => z.y + z.height)),
};
it('fills a single rectangular house with rooms and a full-width front terrace', () => {
  for (let x = bounds.x; x < bounds.right; x++)
    for (let y = bounds.y; y < bounds.bottom; y++)
      expect(
        rooms.some(z => x >= z.x && x < z.x + z.width && y >= z.y && y < z.y + z.height),
        x + ':' + y
      ).toBe(true);
  const terrace = WORLD.zones.find(z => z.id === 'terrace')!;
  expect(terrace.x).toBe(bounds.x);
  expect(terrace.x + terrace.width).toBe(bounds.right);
  expect(terrace.y).toBe(bounds.bottom);
});
it('provides grass and trees on all three non-terrace sides without invading the rooms', () => {
  expect(bounds.x).toBeGreaterThanOrEqual(5);
  expect(WORLD.width - bounds.right).toBeGreaterThanOrEqual(5);
  expect(bounds.y).toBeGreaterThanOrEqual(5);
  const trees = WORLD.props.filter(p => p.kind === 'tree');
  expect(trees.some(p => p.x < bounds.x && p.y > bounds.y && p.y < bounds.bottom)).toBe(true);
  expect(trees.some(p => p.x > bounds.right && p.y > bounds.y && p.y < bounds.bottom)).toBe(true);
  expect(trees.some(p => p.y < bounds.y && p.x > bounds.x && p.x < bounds.right)).toBe(true);
  for (const tree of trees) expect(groundAt(WORLD, tree.x, tree.y), tree.id).toBe('grass');
  for (const x of [bounds.x - 2, bounds.right + 2])
    for (let y = bounds.y; y < bounds.bottom; y++) expect(groundAt(WORLD, x, y)).toBe('grass');
});
it('places the jukebox on the diner back wall, books on the library wall and the call book between side windows', () => {
  const cafe = WORLD.zones.find(z => z.id === 'cafeteria')!,
    library = WORLD.zones.find(z => z.id === 'library')!,
    phone = WORLD.zones.find(z => z.id === 'phone')!;
  const jukebox = WORLD.props.find(p => p.key === 'radio')!;
  expect(jukebox.y - cafe.y).toBeLessThan(1.6);
  for (const shelf of WORLD.props.filter(p => p.activity === 'knowledge' && p.kind === 'shelf'))
    expect(shelf.y - library.y).toBeLessThan(2);
  const book = WORLD.props.find(p => p.key === 'recent-calls')!;
  expect(book.x - phone.x).toBeLessThan(1.6);
  expect(book.y - phone.y).toBeGreaterThan(2);
  expect(book.y + book.depth - phone.y).toBeLessThan(6);
  const nav = compileNavigation(WORLD);
  for (const zone of WORLD.zones)
    expect(findRoute(nav, WORLD.spawn, zone.arrival).length, zone.id).toBeGreaterThan(0);
});

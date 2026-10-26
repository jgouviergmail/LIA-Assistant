import { expect, it } from 'vitest';
import { WORLD, groundAt, onSite, SITE_OFFSET_X } from '../definition';
import { compileNavigation, findRoute, isWalkable } from '../navigation';
import { compilePoseSlots } from '../pose-slots';
import { HOUSE_WALL_RUNS, POND } from '../house-layout';
import { supportedWallArt } from '../wall-mounts';
import { HOUSE_WALLS } from '../house-layout';
import { zoneAt } from '../simulation';

it('keeps every authored doorway and its two approach tiles free of furniture', () => {
  const nav = compileNavigation(WORLD);
  for (const wall of HOUSE_WALL_RUNS)
    for (const offset of wall.openings ?? []) {
      const at = {
        x: wall.x + (wall.axis === 'x' ? offset : 0) + 0.5,
        y: wall.y + (wall.axis === 'y' ? offset : 0) + 0.5,
      };
      for (const side of [-1, 0, 1]) {
        const p = {
          x: at.x + (wall.axis === 'y' ? side : 0),
          y: at.y + (wall.axis === 'x' ? side : 0),
        };
        expect(
          isWalkable(nav, onSite(p)),
          JSON.stringify({ wall: wall.x + ':' + wall.y, offset, p })
        ).toBe(true);
      }
    }
});
it('provides an uninterrupted hall to the front terrace and a garden path around the pond to home', () => {
  const nav = compileNavigation(WORLD);
  for (let y = 33; y <= 53; y++)
    expect(isWalkable(nav, onSite({ x: 31.5, y: y + 0.5 })), 'hall ' + y).toBe(true);
  expect(findRoute(nav, WORLD.spawn, onSite({ x: 54.5, y: 76.5 }))).not.toHaveLength(0);
  expect(groundAt(WORLD, 31 + SITE_OFFSET_X, 60)).toBe('path');
  expect(groundAt(WORLD, 43 + SITE_OFFSET_X, 77)).toBe('path');
  for (let y = POND.y; y < POND.y + POND.height; y++)
    for (let x = POND.x; x < POND.x + POND.width; x++)
      expect(groundAt(WORLD, x + SITE_OFFSET_X, y)).not.toBe('path');
  expect(WORLD.grounds.filter(g => g.kind === 'deck')).toHaveLength(1);
});
it('uses table lamps indoors and preserves safe opposite seats on each terrace table', () => {
  for (const p of WORLD.props.filter(p => p.kind === 'lamp'))
    expect(
      WORLD.zones.some(
        z => z.covered && p.x >= z.x && p.x < z.x + z.width && p.y >= z.y && p.y < z.y + z.height
      ),
      p.id
    ).toBe(false);
  const slots = compilePoseSlots(WORLD);
  expect(slots.filter(s => s.id.startsWith('terrace-chair-'))).toHaveLength(6);
  for (const slot of slots.filter(s => s.id.startsWith('gallery-seat-'))) {
    expect(slot.facing).toBe(2);
    expect(zoneAt(WORLD, slot.approach)).toBe('multimedia');
  }
});

it('mounts every wall feature on a visible full wall and leaves a margin around windows', () => {
  for (const prop of WORLD.props)
    expect(supportedWallArt(prop, HOUSE_WALLS.map(onSite)), prop.id).toBe(true);
  for (const key of ['phone', 'open-loops'])
    expect(
      WORLD.props.some(p => p.key === key),
      key
    ).toBe(true);
  expect(WORLD.props.filter(p => p.kind === 'display')).toHaveLength(2);
  expect(WORLD.props.some(p => p.kind === 'shelf' && zoneAt(WORLD, p) === 'home')).toBe(false);
});

it('places mounted screens and phones outside the solid wall and orders them after their support', () => {
  for (const p of WORLD.props.filter(p =>
    ['wallphone', 'display', 'mirror', 'promiseboard', 'poster'].includes(p.kind)
  )) {
    const wall = HOUSE_WALLS.map(onSite).find(w => w.id === p.support);
    expect(wall, p.id).toBeDefined();
    if (p.facing === 0) expect(p.x, p.id).toBeGreaterThan(wall!.x + 1);
    if (p.facing === 1) expect(p.y, p.id).toBeGreaterThan(wall!.y + 1);
    expect(p.blocking, p.id).toBe(false);
  }
});

it('keeps plants out of the full doorway approach, including avatar shoulder clearance', () => {
  const plants = WORLD.props.filter(p => p.kind === 'plant' || p.kind === 'planter');
  const conflicts: string[] = [];
  for (const wall of HOUSE_WALL_RUNS)
    for (const offset of wall.openings ?? []) {
      const at = onSite({
        x: wall.x + (wall.axis === 'x' ? offset : 0),
        y: wall.y + (wall.axis === 'y' ? offset : 0),
      });
      const apron =
        wall.axis === 'x'
          ? { x: at.x - 0.3, y: at.y - 3, width: 1.6, depth: 7 }
          : { x: at.x - 3, y: at.y - 0.3, width: 7, depth: 1.6 };
      for (const p of plants)
        if (
          p.x < apron.x + apron.width &&
          p.x + p.width > apron.x &&
          p.y < apron.y + apron.depth &&
          p.y + p.depth > apron.y
        )
          conflicts.push(p.id + ' at door ' + wall.x + ':' + wall.y + '/' + offset);
    }
  expect(conflicts).toEqual([]);
});

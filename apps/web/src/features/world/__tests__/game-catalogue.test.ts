import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { compileGameCabinets } from '../game-catalogue';
import { ACTOR_RADIUS, compileNavigation, findRoute, isWalkable } from '../navigation';

it('binds each of three actual cabinets to one distinct rule and a reachable authored approach', () => {
  const cabinets = compileGameCabinets(WORLD);
  expect(cabinets.map(c => c.id)).toEqual([
    'arcade-tic-tac-toe',
    'arcade-four-in-row',
    'arcade-reversi',
  ]);
  expect(new Set(cabinets.map(c => c.game)).size).toBe(3);
  const nav = compileNavigation(WORLD);
  for (const cabinet of cabinets) {
    expect(findRoute(nav, WORLD.spawn, cabinet.approach).at(-1)).toEqual(cabinet.approach);
    expect(WORLD.props.find(p => p.id === cabinet.prop)?.kind).toBe('arcade');
    for (const dx of [-ACTOR_RADIUS, ACTOR_RADIUS])
      for (const dy of [-ACTOR_RADIUS, ACTOR_RADIUS])
        expect(isWalkable(nav, { x: cabinet.approach.x + dx, y: cabinet.approach.y + dy })).toBe(
          true
        );
  }
});
it('refuses missing, duplicated or unregistered cabinet bindings', () => {
  const cabinets = WORLD.props.filter(prop => prop.kind === 'arcade');
  expect(() =>
    compileGameCabinets({ ...WORLD, props: WORLD.props.filter(p => p.id !== cabinets[0].id) })
  ).toThrow('world_arcade_binding');
  expect(() =>
    compileGameCabinets({ ...WORLD, props: [...WORLD.props, { ...cabinets[0], id: 'duplicate' }] })
  ).toThrow('world_arcade_binding');
  expect(() =>
    compileGameCabinets({
      ...WORLD,
      props: WORLD.props.map(p => (p.id === cabinets[0].id ? { ...p, key: 'unknown' } : p)),
    })
  ).toThrow('world_arcade_binding');
});

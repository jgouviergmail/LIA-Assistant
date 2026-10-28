import type { Point, WorldDefinition, WorldProp } from './types';
export const CABINET_GAMES = {
  'arcade-tic-tac-toe': 'tic_tac_toe',
  'arcade-four-in-row': 'four_in_row',
  'arcade-reversi': 'reversi',
} as const;
export type CabinetId = keyof typeof CABINET_GAMES;
export type GameKind = (typeof CABINET_GAMES)[CabinetId];
export interface GameCabinet {
  id: CabinetId;
  prop: string;
  game: GameKind;
  approach: Point;
}
export function cabinetApproach(prop: WorldProp): Point {
  return { x: prop.x + prop.width / 2, y: Math.ceil(prop.y + prop.depth) + 0.5 };
}

/** Stable authored keys bind both renderers and server rules without positional guessing. */
export function compileGameCabinets(world: WorldDefinition): GameCabinet[] {
  const props = world.props.filter(prop => prop.kind === 'arcade');
  if (props.length !== Object.keys(CABINET_GAMES).length) throw new Error('world_arcade_binding');
  return (Object.keys(CABINET_GAMES) as CabinetId[]).map(id => {
    const matches = props.filter(prop => prop.key === id);
    if (matches.length !== 1) throw new Error('world_arcade_binding');
    const prop = matches[0];
    return {
      id,
      prop: prop.id,
      game: CABINET_GAMES[id],
      approach: cabinetApproach(prop),
    };
  });
}

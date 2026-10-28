/** Trusted authored geometry, shared by rendering and the compiled server catalogue. */
import type { PropKind, Tone, WallFinish, WorldProp, WorldZone } from './types';

export interface WallRun {
  x: number;
  y: number;
  length: number;
  axis: 'x' | 'y';
  height: number;
  tone: Tone;
  finish?: WallFinish;
  openings?: readonly number[];
}
export const WALL_DIRECTIONS = [
  { x: 1, y: 0, bit: 1 },
  { x: 0, y: 1, bit: 2 },
  { x: -1, y: 0, bit: 4 },
  { x: 0, y: -1, bit: 8 },
] as const;

/** A junction is one solid, not overlapping independently capped wall segments. */
export function joinWalls(runs: readonly WallRun[]): WorldProp[] {
  const cells = new Map<string, WorldProp>();
  for (const run of runs) {
    for (let offset = 0; offset < run.length; offset++) {
      if (run.openings?.includes(offset)) continue;
      const x = run.x + (run.axis === 'x' ? offset : 0);
      const y = run.y + (run.axis === 'y' ? offset : 0);
      const id = `partition:${x}:${y}`;
      if ((cells.get(id)?.height ?? 0) >= run.height) continue;
      cells.set(id, {
        id,
        kind: 'partition',
        x,
        y,
        width: 1,
        depth: 1,
        height: run.height,
        tone: run.tone,
        wallFinish: run.finish ?? 'plaster',
        blocking: true,
      });
    }
  }
  return [...cells.values()].map(wall => {
    const wallConnections = WALL_DIRECTIONS.reduce(
      (mask, dir) =>
        cells.has(`partition:${wall.x + dir.x}:${wall.y + dir.y}`) ? mask | dir.bit : mask,
      0
    );
    return {
      ...wall,
      wallConnections,
      wallWindow:
        wall.height > 2 &&
        (wallConnections === 5 || wallConnections === 10) &&
        (wall.x + wall.y) % 4 === 0,
    };
  });
}

export type Furnishing = readonly [
  kind: PropKind,
  x: number,
  y: number,
  width: number,
  depth: number,
  height: number,
  tone: Tone,
  key?: string,
  facing?: WorldProp['facing'],
  activity?: WorldProp['activity'],
  support?: string,
];
/** Associate stable authored seat keys with stable table keys, never by proximity. */
export function associateTables(
  props: readonly WorldProp[],
  tables: Readonly<Record<string, readonly string[]>>
): WorldProp[] {
  const seats = new Map<string, string>();
  for (const [table, keys] of Object.entries(tables))
    for (const key of keys) {
      if (seats.has(key)) throw new Error('duplicate_seat_table');
      seats.set(key, table);
    }
  for (const key of seats.keys())
    if (!props.some(prop => prop.key === key)) throw new Error('missing_table_seat');
  return props.map(prop =>
    prop.key && seats.has(prop.key) ? { ...prop, tableKey: seats.get(prop.key) } : prop
  );
}
export function furnish(
  room: Pick<WorldZone, 'x' | 'y'>,
  items: readonly Furnishing[]
): WorldProp[] {
  return items.map(([kind, dx, dy, width, depth, height, tone, key, facing, activity, support]) => {
    const x = room.x + dx,
      y = room.y + dy;
    return {
      id: `${kind}:${x}:${y}`,
      kind,
      x,
      y,
      width,
      depth,
      height,
      tone,
      key,
      activity,
      support,
      facing: facing ?? (kind === 'chair' ? 3 : 1),
      blocking: ![
        'pond',
        'rug',
        'flowers',
        'mosaic',
        'lamp',
        'sign',
        'parasol',
        'poster',
        'display',
        'mirror',
        'bottles',
        'alarm',
        'tablelamp',
        'reeds',
        'promiseboard',
        'wallphone',
        'smartphone',
        'waterlily',
      ].includes(kind),
    };
  });
}

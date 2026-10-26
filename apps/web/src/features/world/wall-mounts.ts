import type { WorldProp } from './types';
const WALL_ART = new Set<WorldProp['kind']>([
  'poster',
  'display',
  'mirror',
  'wallphone',
  'promiseboard',
]);
function wallSpan(prop: WorldProp, walls: readonly WorldProp[]) {
  const vertical = prop.facing === 0 || prop.facing === 2;
  const support = prop.support ? walls.find(w => w.id === prop.support) : undefined;
  const side = vertical ? (support?.x ?? Math.floor(prop.x)) : (support?.y ?? Math.floor(prop.y));
  const start = vertical ? prop.y : prop.x,
    end = start + (vertical ? prop.depth : prop.width);
  const supporting = walls.filter(
    w =>
      (vertical ? w.x : w.y) === side &&
      (vertical ? w.y : w.x) < end &&
      (vertical ? w.y : w.x) + 1 > start
  );
  return { vertical, side, start, end, supporting };
}
/** Cutaway partitions cannot carry floating wall art; window bays retain a clear margin. */
export function supportedWallArt(prop: WorldProp, walls: readonly WorldProp[]): boolean {
  if (!WALL_ART.has(prop.kind)) return true;
  const { vertical, side, start, end, supporting } = wallSpan(prop, walls);
  if (!supporting.length || supporting.some(w => w.height < prop.height - 0.1)) return false;
  const covered = supporting.reduce(
    (n, w) =>
      n +
      Math.max(
        0,
        Math.min(end, (vertical ? w.y : w.x) + 1) - Math.max(start, vertical ? w.y : w.x)
      ),
    0
  );
  if (covered < end - start - 0.01) return false;
  return !walls.some(
    w =>
      w.wallWindow &&
      (vertical ? w.x : w.y) === side &&
      (vertical ? w.y : w.x) < end + 0.25 &&
      (vertical ? w.y : w.x) + 1 > start - 0.25
  );
}
/** Author markers live in their wall bay; the visible mesh sits on the room-facing surface. */
export function mountWallArt(prop: WorldProp, walls: readonly WorldProp[]): WorldProp | null {
  if (!WALL_ART.has(prop.kind)) return prop;
  if (!supportedWallArt(prop, walls)) return null;
  const { side, supporting } = wallSpan(prop, walls);
  const support = supporting.reduce((a, b) => (a.x + a.y > b.x + b.y ? a : b));
  const facing = prop.facing ?? 1;
  const x = facing === 0 ? side + 1.005 : facing === 2 ? side - prop.width - 0.005 : prop.x;
  const y = facing === 1 ? side + 1.005 : facing === 3 ? side - prop.depth - 0.005 : prop.y;
  return { ...prop, x, y, support: support.id, blocking: false };
}

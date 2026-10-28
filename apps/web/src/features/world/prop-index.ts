import { project } from './geometry';
import { spriteFrame } from './art/painter';
import type { Rect, WorldProp } from './types';
import { cosmeticPropTarget } from './cosmetic-interactions';

export function hasPickSurface(prop: WorldProp): boolean {
  return prop.height >= 0.1 || cosmeticPropTarget(prop) !== null;
}

interface Entry {
  prop: WorldProp;
  bounds: Rect;
  order: number;
}
const CELL = 128;
const MAX_CELLS = 4096;
function valid(area: Rect): boolean {
  return (
    Number.isFinite(area.x + area.y + area.width + area.height) && area.width > 0 && area.height > 0
  );
}
function intersects(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}
function cells(area: Rect) {
  const x = Math.floor(area.x / CELL),
    y = Math.floor(area.y / CELL);
  const right = Math.floor((area.x + area.width) / CELL),
    bottom = Math.floor((area.y + area.height) / CELL);
  if (![x, y, right, bottom].every(Number.isSafeInteger)) return null;
  return { x, y, right, bottom, count: (right - x + 1) * (bottom - y + 1) };
}
/** Immutable scene geometry only. Rebuild on private-layout changes; moving actors are never indexed.
 * Query results retain authored draw order and contain every intersecting allocated sprite.
 */
export class WorldPropIndex {
  private entries: Entry[] = [];
  private buckets = new Map<string, Entry[]>();
  constructor(props: readonly WorldProp[]) {
    for (const [order, prop] of props.entries()) {
      if (!hasPickSurface(prop)) continue;
      const at = project(prop),
        frame = spriteFrame(prop.width, prop.depth, Math.max(prop.height, 2.5));
      const bounds = {
        x: at.x - frame.anchorX,
        y: at.y - frame.anchorY,
        width: frame.width,
        height: frame.height,
      };
      if (!valid(bounds)) throw new RangeError('world_prop_bounds_invalid');
      const entry = { prop, bounds, order };
      this.entries.push(entry);
      this.insert(entry);
    }
  }
  private insert(entry: Entry): void {
    const range = cells(entry.bounds);
    if (!range || range.count > MAX_CELLS) throw new RangeError('world_prop_bounds_limit');
    for (let y = range.y; y <= range.bottom; y++)
      for (let x = range.x; x <= range.right; x++) {
        const key = x + ':' + y,
          bucket = this.buckets.get(key);
        if (bucket) bucket.push(entry);
        else this.buckets.set(key, [entry]);
      }
  }
  query(area: Rect): WorldProp[] {
    if (!valid(area)) return [];
    const range = cells(area);
    if (!range) return [];
    if (range.count > MAX_CELLS)
      return this.entries.filter(entry => intersects(entry.bounds, area)).map(entry => entry.prop);
    const found = new Set<Entry>();
    for (let y = range.y; y <= range.bottom; y++)
      for (let x = range.x; x <= range.right; x++)
        for (const entry of this.buckets.get(x + ':' + y) ?? [])
          if (intersects(entry.bounds, area)) found.add(entry);
    return [...found].sort((a, b) => a.order - b.order).map(entry => entry.prop);
  }
  clear(): void {
    this.entries = [];
    this.buckets.clear();
  }
}

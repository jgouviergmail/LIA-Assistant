import type { Ground, WorldProp } from '../types';

/** Small authored texture families, independent of account/profile or message data. */
function coordinateHash(x: number, y: number): number {
  let value = Math.imul(x, 374761393) ^ Math.imul(y, 668265263);
  value = Math.imul(value ^ (value >>> 13), 1274126177);
  return (value ^ (value >>> 16)) >>> 0;
}
const VARIED = new Set<WorldProp['kind']>([
  'chair',
  'table',
  'tablelamp',
  'poster',
  'archive',
  'machine',
  'tree',
  'plant',
  'planter',
  'flowers',
  'easel',
  'shelf',
  'vegetable',
  'rock',
  'reeds',
]);
export function propStyleVariant(prop: WorldProp): number {
  return VARIED.has(prop.kind)
    ? coordinateHash(Math.floor(prop.x * 4), Math.floor(prop.y * 4)) % 3
    : 0;
}
export function groundVariant(x: number, y: number): number {
  return coordinateHash(x, y) % 8;
}
export function propTextureKey(prop: WorldProp, privateAppearance: boolean, mask: boolean): string {
  return [
    privateAppearance ? 'private' : 'neutral',
    prop.kind,
    prop.wallFinish ?? 'plaster',
    prop.wallConnections ?? 0,
    prop.wallWindow ? 1 : 0,
    prop.width,
    prop.depth,
    prop.height,
    prop.facing ?? 1,
    prop.tone,
    prop.activity ?? '',
    propStyleVariant(prop),
    mask ? 'mask' : 'color',
  ].join(':');
}

/** Checker parity is global, including across cached chunk boundaries. */
export function floorVariant(kind: Ground, x: number, y: number): number {
  return kind === 'checker' ? (Math.floor(x / 2) + Math.floor(y / 2)) % 2 : groundVariant(x, y);
}

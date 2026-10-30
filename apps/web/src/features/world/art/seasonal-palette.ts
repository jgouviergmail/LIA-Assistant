import type { Season } from '../season';
import type { WorldProp } from '../types';
export const SEASONAL_KINDS: ReadonlySet<WorldProp['kind']> = new Set([
  'tree',
  'plant',
  'planter',
  'flowers',
]);
const PALETTES = {
  neutral: { leaf: '#438953', blossom: '#df87aa', petal: '#e8756c', flowers: 0 },
  spring: { leaf: '#7aab56', blossom: '#eba2bd', petal: '#e875a5', flowers: 2 },
  summer: { leaf: '#398755', blossom: '#d980aa', petal: '#edb447', flowers: 1 },
  autumn: { leaf: '#b97c3d', blossom: '#ca8859', petal: '#d47743', flowers: -1 },
  winter: { leaf: '#75938b', blossom: '#bacac3', petal: '#c4d9dc', flowers: -2 },
} as const;
export function seasonalPalette(season: Season) {
  return PALETTES[season];
}

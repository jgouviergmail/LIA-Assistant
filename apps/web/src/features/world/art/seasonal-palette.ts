import type { Season } from '../season';
import type { WorldProp } from '../types';
export const SEASONAL_KINDS: ReadonlySet<WorldProp['kind']> = new Set([
  'tree',
  'plant',
  'planter',
  'flowers',
]);
const PALETTES = {
  neutral: { leaf: '#438951', blossom: '#df699c', petal: '#e86b67', flowers: 0 },
  spring: { leaf: '#78aa56', blossom: '#ed9fbd', petal: '#e881ae', flowers: 2 },
  summer: { leaf: '#378452', blossom: '#d783aa', petal: '#efb849', flowers: 1 },
  autumn: { leaf: '#b97c3d', blossom: '#ca8859', petal: '#d47743', flowers: -1 },
  winter: { leaf: '#75938b', blossom: '#bacac3', petal: '#c4d9dc', flowers: -2 },
} as const;
export function seasonalPalette(season: Season) {
  return PALETTES[season];
}

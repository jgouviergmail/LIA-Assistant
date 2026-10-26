/** Finite authored art vocabulary. Pure data: no API, state, schema library or account context. */
export const AVATAR_HAIR = ['bald', 'short', 'long', 'curly', 'ponytail', 'mohawk'] as const;
export const AVATAR_COLORS = {
  charcoal: '#252c38',
  brown: '#594034',
  silver: '#b6bdc7',
  gold: '#edbf54',
  red: '#c93c42',
  green: '#369266',
  blue: '#397bd2',
  violet: '#905ac0',
  cream: '#f0e4c9',
  orange: '#e48336',
} as const;
export const AVATAR_SKINS = {
  porcelain: '#f3d5bc',
  sand: '#dfb594',
  caramel: '#cfa384',
  walnut: '#9e6f50',
  espresso: '#674730',
} as const;
export const AVATAR_COLOR_IDS = [
  'charcoal',
  'brown',
  'silver',
  'gold',
  'red',
  'green',
  'blue',
  'violet',
  'cream',
  'orange',
] as const;
export const AVATAR_SKIN_IDS = ['porcelain', 'sand', 'caramel', 'walnut', 'espresso'] as const;
export const AVATAR_OUTFITS = ['casual', 'suit', 'dress'] as const;
export const AVATAR_HEADWEAR = ['none', 'cap', 'beanie', 'hat'] as const;

export interface AvatarAppearance {
  readonly version: 1;
  readonly skin: (typeof AVATAR_SKIN_IDS)[number];
  readonly hair: (typeof AVATAR_HAIR)[number];
  readonly hair_color: (typeof AVATAR_COLOR_IDS)[number];
  readonly outfit: (typeof AVATAR_OUTFITS)[number];
  readonly outfit_color: (typeof AVATAR_COLOR_IDS)[number];
  readonly headwear: (typeof AVATAR_HEADWEAR)[number];
  readonly headwear_color: (typeof AVATAR_COLOR_IDS)[number];
  readonly glasses: boolean;
}
export const DEFAULT_AVATAR: AvatarAppearance = Object.freeze({
  version: 1,
  skin: 'caramel',
  hair: 'short',
  hair_color: 'brown',
  outfit: 'casual',
  outfit_color: 'green',
  headwear: 'none',
  headwear_color: 'blue',
  glasses: false,
});
export function appearanceSignature(value: AvatarAppearance): string {
  return [
    value.version,
    value.skin,
    value.hair,
    value.hair_color,
    value.outfit,
    value.outfit_color,
    value.headwear,
    value.headwear_color,
    Number(value.glasses),
  ].join(':');
}

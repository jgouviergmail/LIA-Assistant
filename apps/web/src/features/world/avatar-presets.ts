/** Authored combinations only; selection never persists a presentation or preset ID. */
import { DEFAULT_AVATAR, appearanceSignature, type AvatarAppearance } from './avatar-catalogue';
export interface AvatarPreset {
  readonly id: string;
  readonly presentation: 'masculine' | 'feminine';
  readonly titleKey: string;
  readonly appearance: AvatarAppearance;
}
function preset(
  id: string,
  presentation: AvatarPreset['presentation'],
  skin: AvatarAppearance['skin'],
  choices: Partial<AvatarAppearance>
): AvatarPreset {
  return Object.freeze({
    id,
    presentation,
    titleKey: 'world.avatar.presets.' + id,
    appearance: Object.freeze({ ...DEFAULT_AVATAR, skin, ...choices }),
  });
}
export const AVATAR_PRESETS: readonly AvatarPreset[] = Object.freeze([
  preset('M01', 'masculine', 'porcelain', {
    hair: 'short',
    hair_color: 'gold',
    outfit_color: 'blue',
  }),
  preset('M02', 'masculine', 'sand', {
    hair: 'curly',
    hair_color: 'charcoal',
    outfit_color: 'cream',
    glasses: true,
  }),
  preset('M03', 'masculine', 'caramel', {
    hair: 'short',
    outfit: 'suit',
    outfit_color: 'charcoal',
  }),
  preset('M04', 'masculine', 'walnut', {
    hair: 'mohawk',
    hair_color: 'red',
    outfit_color: 'violet',
    headwear: 'beanie',
    headwear_color: 'orange',
  }),
  preset('M05', 'masculine', 'espresso', {
    hair: 'bald',
    outfit: 'suit',
    outfit_color: 'cream',
    headwear: 'hat',
    headwear_color: 'charcoal',
  }),
  preset('F01', 'feminine', 'porcelain', {
    hair: 'ponytail',
    hair_color: 'brown',
    outfit_color: 'red',
  }),
  preset('F02', 'feminine', 'sand', {
    hair: 'long',
    hair_color: 'charcoal',
    outfit: 'suit',
    outfit_color: 'green',
    glasses: true,
  }),
  preset('F03', 'feminine', 'caramel', {
    hair: 'curly',
    hair_color: 'brown',
    outfit: 'dress',
    outfit_color: 'blue',
  }),
  preset('F04', 'feminine', 'walnut', {
    hair: 'short',
    hair_color: 'silver',
    outfit_color: 'orange',
    headwear: 'cap',
    headwear_color: 'violet',
  }),
  preset('F05', 'feminine', 'espresso', {
    hair: 'long',
    hair_color: 'charcoal',
    outfit: 'dress',
    outfit_color: 'violet',
    headwear: 'hat',
    headwear_color: 'cream',
  }),
]);
export function matchingAvatarPreset(appearance: AvatarAppearance): AvatarPreset | null {
  const signature = appearanceSignature(appearance);
  return AVATAR_PRESETS.find(item => appearanceSignature(item.appearance) === signature) ?? null;
}

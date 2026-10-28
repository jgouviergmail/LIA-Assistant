import { expect, it } from 'vitest';
import { AVATAR_PRESETS, matchingAvatarPreset } from '../avatar-presets';
import { AVATAR_SKIN_IDS, appearanceSignature } from '../avatar-catalogue';
import { avatarAppearanceSchema } from '../avatar-protocol';

it('offers ten distinct editable combinations, five presentations and every skin in each set', () => {
  expect(AVATAR_PRESETS).toHaveLength(10);
  expect(new Set(AVATAR_PRESETS.map(p => p.id)).size).toBe(10);
  expect(new Set(AVATAR_PRESETS.map(p => appearanceSignature(p.appearance))).size).toBe(10);
  for (const presentation of ['masculine', 'feminine'] as const) {
    const group = AVATAR_PRESETS.filter(p => p.presentation === presentation);
    expect(group).toHaveLength(5);
    expect(group.map(p => p.appearance.skin).sort()).toEqual([...AVATAR_SKIN_IDS].sort());
  }
  for (const preset of AVATAR_PRESETS) {
    expect(avatarAppearanceSchema.safeParse(preset.appearance).success).toBe(true);
    expect(matchingAvatarPreset(preset.appearance)?.id).toBe(preset.id);
    expect(
      matchingAvatarPreset({ ...preset.appearance, glasses: !preset.appearance.glasses })
    ).toBeNull();
  }
});

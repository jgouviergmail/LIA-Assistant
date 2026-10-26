import { describe, expect, it } from 'vitest';
import { avatarAppearanceSchema, avatarViewSchema, DEFAULT_AVATAR, appearanceSignature, AVATAR_HAIR } from '../avatar-protocol';

describe('declared avatar contract', () => {
  it('accepts finite choices and refuses executable or private content', () => {
    expect(avatarAppearanceSchema.parse({})).toEqual(DEFAULT_AVATAR);
    for (const patch of [
      { hair: 'https://example.invalid/a' }, { hair_color: '#abcdef' },
      { glasses: 'true' }, { profile: 'PRIVATE' }, { version: true }, { version: 2 },
    ]) expect(avatarAppearanceSchema.safeParse({ ...DEFAULT_AVATAR, ...patch }).success).toBe(false);
    expect(new Set(AVATAR_HAIR.map(hair => appearanceSignature({ ...DEFAULT_AVATAR, hair }))).size).toBe(AVATAR_HAIR.length);
  });
  it('keeps cache identity independent from object ordering and sensitive metadata', () => {
    const value = { ...DEFAULT_AVATAR, hair: 'long' as const, outfit: 'dress' as const };
    const reordered = avatarAppearanceSchema.parse(Object.fromEntries(Object.entries(value).reverse()));
    expect(appearanceSignature(value)).toBe(appearanceSignature(reordered));
    expect(appearanceSignature({ ...DEFAULT_AVATAR, glasses: true })).not.toBe(appearanceSignature(DEFAULT_AVATAR));
    expect(appearanceSignature({ ...DEFAULT_AVATAR, headwear: 'cap' })).not.toBe(appearanceSignature(DEFAULT_AVATAR));
  });
  it('bounds owner preferences and preserves complete Unicode names', () => {
    const value = {
      owner_id: '4010c2c2-4bd0-4d21-9c08-b4502db25d72',
      public_name: '🌻'.repeat(24),
      needs_setup: false, needs_reset: false,
      preferences: { version: 1, revision: 1, appearance: DEFAULT_AVATAR },
    };
    expect(avatarViewSchema.safeParse(value).success).toBe(true);
    expect(avatarViewSchema.safeParse({ ...value, public_name: '🌻'.repeat(25) }).success).toBe(false);
    expect(avatarViewSchema.safeParse({ ...value, owner_id: 'another-person' }).success).toBe(false);
    for (const revision of [true, -1, 1.5, Number.MAX_SAFE_INTEGER + 1])
      expect(avatarViewSchema.safeParse({ ...value, preferences: { ...value.preferences, revision } }).success).toBe(false);
  });
});

/** Non-secret, bounded operator campaign identifier; empty means no campaign. */
export function normalizeAvatarStyleRolloutId(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const id = value.trim();
  return /^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,79}$/.test(id) ? id : null;
}

export interface RuntimeUiConfig {
  avatarStyleRolloutId: string | null;
}

export function avatarStyleRolloutIdFromConfig(value: unknown): string | null {
  if (!value || typeof value !== 'object' || !('avatarStyleRolloutId' in value)) return null;
  return normalizeAvatarStyleRolloutId(value.avatarStyleRolloutId);
}

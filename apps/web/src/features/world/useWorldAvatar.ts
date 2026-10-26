'use client';
import { avatarViewSchema, type AvatarView, type AvatarWrite } from './avatar-protocol';
import { useWorldOwnerPreferences } from './useWorldOwnerPreferences';

export function useWorldAvatar(ownerId: string, enabled: boolean) {
  const { value, ...state } = useWorldOwnerPreferences<AvatarView, AvatarWrite>(
    ownerId,
    enabled,
    'avatar',
    avatarViewSchema
  );
  return { ...state, avatar: value };
}

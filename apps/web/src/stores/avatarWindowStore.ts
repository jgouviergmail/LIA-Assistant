'use client';

import { create } from 'zustand';
import { normalizeFloatingPosition, sameFloatingPosition } from '@/lib/floating-position';
import { persist } from 'zustand/middleware';
import type { FloatingPosition } from '@/hooks/useFloatingDrag';

export const AVATAR_SIZES = { sm: 160, md: 240, lg: 320 } as const;
export type AvatarSize = keyof typeof AVATAR_SIZES;
export const AVATAR_WINDOW_STORAGE_KEY = 'lia.avatarWindow';
interface WindowState {
  size: AvatarSize;
  position: FloatingPosition | null;
  setSize(size: AvatarSize): void;
  setPosition(position: FloatingPosition): void;
}
function geometry(value: unknown): { size: AvatarSize; position: FloatingPosition | null } {
  if (!value || typeof value !== 'object') return { size: 'sm', position: null };
  const size = 'size' in value && (value.size === 'md' || value.size === 'lg') ? value.size : 'sm';
  const p = 'position' in value ? value.position : null;
  return { size, position: normalizeFloatingPosition(p) };
}
/** Geometry only: no account opt-in, face, stream or credential is persisted. */
export const useAvatarWindowStore = create<WindowState>()(
  persist(
    set => ({
      size: 'sm',
      position: null,
      setSize: size => set({ size }),
      setPosition: value =>
        set(s => {
          const position = normalizeFloatingPosition(value);
          return sameFloatingPosition(s.position, position) ? s : { position };
        }),
    }),
    {
      name: AVATAR_WINDOW_STORAGE_KEY,
      partialize: state => ({ size: state.size, position: state.position }),
      merge: (stored, current) => ({ ...current, ...geometry(stored) }),
    }
  )
);

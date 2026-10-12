'use client';

/**
 * Zustand store for the expressive-eyes widget display preferences.
 *
 * Persists visibility, size preset and position (viewport percentages, so the
 * widget survives resolution and orientation changes) to localStorage — the
 * same `persist` pattern as `voiceModeStore`. Pure display preference of the
 * device: deliberately outside the SEC-035 purge registry (see the key's
 * rationale in `lib/constants.ts`).
 */

import { create } from 'zustand';
import { normalizeFloatingPosition, sameFloatingPosition } from '@/lib/floating-position';
import { persist } from 'zustand/middleware';

import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';
import { DEFAULT_EYE_STYLE, isValidEyeStyle, type EyeStyleId } from '@/components/eyes/eye-styles';
import { normalizeAvatarStyleRolloutId } from '@/lib/runtime-ui';

export type EyesSize = 'sm' | 'md' | 'lg' | 'xl';

/** Persisted size setting: a preset, or 'auto' (responsive sizing —
 * small on phones, large on desktop; resolved by the widget). */
export type EyesSizeSetting = EyesSize | 'auto';

/** Ordered size presets the size button cycles through. */
export const EYES_SIZES: readonly EyesSize[] = ['sm', 'md', 'lg', 'xl'];

/** Widget anchor position as percentages of the viewport (top-left corner). */
export interface EyesPosition {
  xPct: number;
  yPct: number;
}

/**
 * Where the widget is mounted. The chat docks it in its header and clamps it
 * off the Delete button; the landing (public, often visited without an
 * account) has neither, so a spot dragged there must not become the chat's
 * spot — each surface keeps its own position, everything else is shared.
 */
export type EyesSurface = 'chat' | 'landing';

export interface EyesWidgetStore {
  /** Whether the widget renders (false → restore dot only). */
  visible: boolean;
  size: EyesSizeSetting;
  /** Selected look, from the eye-style registry. */
  style: EyeStyleId;
  /** Custom position on the chat, or null for the default docked spot. */
  position: EyesPosition | null;
  /** Custom position on the landing, or null for its default corner. */
  landingPosition: EyesPosition | null;
  /** Last operator campaign applied on this browser origin, not an account preference. */
  appliedAvatarStyleRolloutId: string | null;

  setVisible: (visible: boolean) => void;
  setSize: (size: EyesSizeSetting) => void;
  cycleSize: () => void;
  /** Invalid ids (stale persisted value after a style removal) are ignored. */
  setStyle: (style: EyeStyleId) => void;
  setPosition: (position: EyesPosition) => void;
  setLandingPosition: (position: EyesPosition) => void;
  applyAvatarStyleRollout: (id: string) => void;
  reset: () => void;
}

const DEFAULTS = {
  visible: true,
  size: 'xl' as EyesSizeSetting,
  style: DEFAULT_EYE_STYLE,
  position: null as EyesPosition | null,
  landingPosition: null as EyesPosition | null,
};

export const useEyesWidgetStore = create<EyesWidgetStore>()(
  persist(
    (set, get) => ({
      ...DEFAULTS,
      appliedAvatarStyleRolloutId: null,

      setVisible: visible => set({ visible }),

      setSize: size => set({ size }),

      cycleSize: () =>
        set(s => ({
          // From 'auto' the first click lands on the middle preset; after
          // that the button walks the ordered list.
          size:
            s.size === 'auto'
              ? 'md'
              : EYES_SIZES[(EYES_SIZES.indexOf(s.size) + 1) % EYES_SIZES.length],
        })),

      setStyle: style => {
        if (isValidEyeStyle(style)) set({ style });
      },

      setPosition: value =>
        set(s => {
          const position = normalizeFloatingPosition(value);
          return sameFloatingPosition(s.position, position) ? s : { position };
        }),

      setLandingPosition: value =>
        set(s => {
          const landingPosition = normalizeFloatingPosition(value);
          return sameFloatingPosition(s.landingPosition, landingPosition) ? s : { landingPosition };
        }),

      applyAvatarStyleRollout: value => {
        const id = normalizeAvatarStyleRolloutId(value);
        const previous = get();
        if (!id || previous.appliedAvatarStyleRolloutId === id) return;
        try {
          set({ style: 'bip', appliedAvatarStyleRolloutId: id });
        } catch {
          // Persist updates memory before writing localStorage. Quota/privacy
          // refusal must not leave an unrecorded campaign replacing the choice.
          try {
            set({
              style: previous.style,
              appliedAvatarStyleRolloutId: previous.appliedAvatarStyleRolloutId,
            });
          } catch {
            // Memory was restored before this second storage refusal.
          }
        }
      },

      // A manual reset restores display defaults, but does not replay a campaign.
      reset: () => set(DEFAULTS),
    }),
    {
      name: EYES_WIDGET_PREFS_KEY,
      partialize: s => ({
        visible: s.visible,
        size: s.size,
        style: s.style,
        position: s.position,
        landingPosition: s.landingPosition,
        appliedAvatarStyleRolloutId: s.appliedAvatarStyleRolloutId,
      }),
      // A persisted style that no longer exists in the registry falls back to
      // the default instead of rendering an unstyled widget.
      merge: (persisted, current) => {
        const p = persisted as Partial<EyesWidgetStore> | undefined;
        return {
          ...current,
          ...p,
          position: normalizeFloatingPosition(p?.position),
          landingPosition: normalizeFloatingPosition(p?.landingPosition),
          style: isValidEyeStyle(p?.style) ? p.style : DEFAULT_EYE_STYLE,
          appliedAvatarStyleRolloutId: normalizeAvatarStyleRolloutId(
            p?.appliedAvatarStyleRolloutId
          ),
        };
      },
    }
  )
);

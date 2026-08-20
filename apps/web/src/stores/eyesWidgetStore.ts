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
import { persist } from 'zustand/middleware';

import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';
import { DEFAULT_EYE_STYLE, isValidEyeStyle, type EyeStyleId } from '@/components/eyes/eye-styles';

export type EyesSize = 'sm' | 'md' | 'lg';

/** Persisted size setting: a preset, or 'auto' (responsive default —
 * small on phones, large on desktop; resolved by the widget). */
export type EyesSizeSetting = EyesSize | 'auto';

/** Ordered size presets the size button cycles through. */
export const EYES_SIZES: readonly EyesSize[] = ['sm', 'md', 'lg'];

/** Widget anchor position as percentages of the viewport (top-left corner). */
export interface EyesPosition {
  xPct: number;
  yPct: number;
}

export interface EyesWidgetStore {
  /** Whether the widget renders (false → restore dot only). */
  visible: boolean;
  size: EyesSizeSetting;
  /** Selected look, from the eye-style registry. */
  style: EyeStyleId;
  /** Custom position, or null for the default docked spot. */
  position: EyesPosition | null;

  setVisible: (visible: boolean) => void;
  setSize: (size: EyesSizeSetting) => void;
  cycleSize: () => void;
  /** Invalid ids (stale persisted value after a style removal) are ignored. */
  setStyle: (style: EyeStyleId) => void;
  setPosition: (position: EyesPosition) => void;
  reset: () => void;
}

const DEFAULTS = {
  visible: true,
  size: 'auto' as EyesSizeSetting,
  style: DEFAULT_EYE_STYLE,
  position: null as EyesPosition | null,
};

function clampPct(value: number): number {
  return Math.min(100, Math.max(0, value));
}

export const useEyesWidgetStore = create<EyesWidgetStore>()(
  persist(
    set => ({
      ...DEFAULTS,

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

      setPosition: position =>
        set({ position: { xPct: clampPct(position.xPct), yPct: clampPct(position.yPct) } }),

      reset: () => set(DEFAULTS),
    }),
    {
      name: EYES_WIDGET_PREFS_KEY,
      partialize: s => ({
        visible: s.visible,
        size: s.size,
        style: s.style,
        position: s.position,
      }),
      // A persisted style that no longer exists in the registry falls back to
      // the default instead of rendering an unstyled widget.
      merge: (persisted, current) => {
        const p = persisted as Partial<EyesWidgetStore> | undefined;
        return {
          ...current,
          ...p,
          style: isValidEyeStyle(p?.style) ? p.style : DEFAULT_EYE_STYLE,
        };
      },
    }
  )
);

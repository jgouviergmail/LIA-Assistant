/**
 * The accent themes, and the storage key they are remembered under.
 *
 * Extracted from `theme-context.tsx` so the blocking anti-FOUC script can share
 * the exact same list. A second, hand-typed copy inside a stringified script is
 * precisely the kind of duplication that goes stale silently: add a sixth
 * accent, forget the script, and that accent alone flashes on every load.
 *
 * Plain module (no `'use client'`) so a server component can import it without
 * dragging a client boundary along.
 */

export const COLOR_THEMES = ['default', 'ocean', 'forest', 'sunset', 'slate'] as const;

export type ColorThemeName = (typeof COLOR_THEMES)[number];

/** The accent that needs no `data-theme` attribute — it IS the base palette. */
export const DEFAULT_COLOR_THEME: ColorThemeName = 'default';

/** localStorage key holding the chosen accent. */
export const COLOR_THEME_STORAGE_KEY = 'color-theme';

export function isColorThemeName(value: unknown): value is ColorThemeName {
  return typeof value === 'string' && (COLOR_THEMES as readonly string[]).includes(value);
}

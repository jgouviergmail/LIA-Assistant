'use client';

import { createContext, useContext, type ReactNode } from 'react';
import { DEFAULT_ICON_STYLE, type IconStyle } from '@/lib/icon-style';

/** Also works on public pages and in standalone renderers: Fluent is the default. */
export const IconStyleContext = createContext<IconStyle>(DEFAULT_ICON_STYLE);

export function useIconStyle(): IconStyle {
  return useContext(IconStyleContext);
}

/**
 * A filled, coloured surface draws its glyphs in its label colour.
 *
 * The coloured families paint fixed hues (Fluent's blues and violets) that
 * clash with any solid background, a red one worst of all (owner, 2026-11-11).
 * Lucide strokes `currentColor`, so the glyph takes the surface's foreground.
 */
export function MonochromeIcons({
  children,
  enabled = true,
}: {
  children: ReactNode;
  enabled?: boolean;
}) {
  const inherited = useIconStyle();
  return (
    <IconStyleContext.Provider value={enabled ? 'lucide' : inherited}>
      {children}
    </IconStyleContext.Provider>
  );
}

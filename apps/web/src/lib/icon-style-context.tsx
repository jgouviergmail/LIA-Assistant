'use client';

import { createContext, useContext } from 'react';
import { DEFAULT_ICON_STYLE, type IconStyle } from '@/lib/icon-style';

/** Also works on public pages and in standalone renderers: Fluent is the default. */
export const IconStyleContext = createContext<IconStyle>(DEFAULT_ICON_STYLE);

export function useIconStyle(): IconStyle {
  return useContext(IconStyleContext);
}

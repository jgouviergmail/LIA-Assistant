'use client';

import * as React from 'react';
import {
  type FontFamilyName,
  FONT_FAMILY_NAMES,
  DEFAULT_FONT_FAMILY,
  FONT_STORAGE_KEY,
  isValidFontFamily,
} from '@/constants/fonts';

// Re-export type for convenience
export type { FontFamilyName };

interface FontContextValue {
  fontFamily: FontFamilyName;
  setFontFamily: (font: FontFamilyName) => void;
}

const FontContext = React.createContext<FontContextValue | undefined>(undefined);

export function FontProvider({ children }: { children: React.ReactNode }) {
  const [fontFamily, setFontFamilyState] = React.useState<FontFamilyName>(DEFAULT_FONT_FAMILY);
  const [mounted, setMounted] = React.useState(false);

  // Load font from localStorage on mount
  React.useEffect(() => {
    const stored = localStorage.getItem(FONT_STORAGE_KEY);
    if (stored && isValidFontFamily(stored)) {
      setFontFamilyState(stored);
    }
    setMounted(true);
  }, []);

  // Apply data-font attribute to html element
  React.useEffect(() => {
    if (!mounted) return;

    const html = document.documentElement;

    // Remove old data-font
    html.removeAttribute('data-font');

    // Apply new font (except for system which uses default)
    if (fontFamily !== 'system') {
      html.setAttribute('data-font', fontFamily);
    }
  }, [fontFamily, mounted]);

  const setFontFamily = React.useCallback((font: FontFamilyName) => {
    const validFont = isValidFontFamily(font) ? font : DEFAULT_FONT_FAMILY;
    if (validFont !== font) {
      console.warn(`Invalid font family: ${font}. Using default.`);
    }
    setFontFamilyState(validFont);
    localStorage.setItem(FONT_STORAGE_KEY, validFont);
  }, []);

  const value = React.useMemo(() => ({ fontFamily, setFontFamily }), [fontFamily, setFontFamily]);

  return <FontContext.Provider value={value}>{children}</FontContext.Provider>;
}

export function useFontFamily() {
  const context = React.useContext(FontContext);
  if (context === undefined) {
    throw new Error('useFontFamily must be used within a FontProvider');
  }
  return context;
}

/**
 * Get all valid font family names.
 * Useful for validation or iteration.
 */
export function getValidFontFamilies(): readonly FontFamilyName[] {
  return FONT_FAMILY_NAMES;
}

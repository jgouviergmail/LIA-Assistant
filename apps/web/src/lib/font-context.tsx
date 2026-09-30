'use client';

import * as React from 'react';
import {
  type FontFamilyName,
  FONT_FAMILY_NAMES,
  DEFAULT_FONT_FAMILY,
  DEFAULT_FONT_SIZE_PX,
  FONT_SIZE_CSS_VAR,
  FONT_SIZE_STORAGE_KEY,
  FONT_STORAGE_KEY,
  fontSizeScale,
  isValidFontFamily,
  isValidFontSize,
  parseStoredFontSize,
} from '@/constants/fonts';

// Re-export type for convenience
export type { FontFamilyName };

interface FontContextValue {
  fontFamily: FontFamilyName;
  setFontFamily: (font: FontFamilyName) => void;
  /** Interface text size in px at the browser's default root size. */
  fontSize: number;
  setFontSize: (px: number) => void;
}

const FontContext = React.createContext<FontContextValue | undefined>(undefined);

// localStorage THROWS, rather than returning null, in some privacy modes: a
// display preference must degrade to "not remembered", never break the tree.
function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Not remembered on this device; the choice still applies to this page.
  }
}

export function FontProvider({ children }: { children: React.ReactNode }) {
  const [fontFamily, setFontFamilyState] = React.useState<FontFamilyName>(DEFAULT_FONT_FAMILY);
  const [fontSize, setFontSizeState] = React.useState<number>(DEFAULT_FONT_SIZE_PX);
  const [mounted, setMounted] = React.useState(false);

  // Load the stored preferences on mount (the pre-paint script already applied them)
  React.useEffect(() => {
    const stored = readStorage(FONT_STORAGE_KEY);
    if (stored && isValidFontFamily(stored)) {
      setFontFamilyState(stored);
    }
    const storedSize = parseStoredFontSize(readStorage(FONT_SIZE_STORAGE_KEY));
    if (storedSize !== null) {
      setFontSizeState(storedSize);
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

  // Apply the text size: every font size of the stylesheet is multiplied by it.
  React.useEffect(() => {
    if (!mounted) return;

    const style = document.documentElement.style;
    if (fontSize === DEFAULT_FONT_SIZE_PX) {
      style.removeProperty(FONT_SIZE_CSS_VAR);
    } else {
      style.setProperty(FONT_SIZE_CSS_VAR, String(fontSizeScale(fontSize)));
    }
  }, [fontSize, mounted]);

  const setFontFamily = React.useCallback((font: FontFamilyName) => {
    const validFont = isValidFontFamily(font) ? font : DEFAULT_FONT_FAMILY;
    if (validFont !== font) {
      console.warn(`Invalid font family: ${font}. Using default.`);
    }
    setFontFamilyState(validFont);
    writeStorage(FONT_STORAGE_KEY, validFont);
  }, []);

  const setFontSize = React.useCallback((px: number) => {
    // Refused, never clamped: the settings only offer valid steps.
    if (!isValidFontSize(px)) return;
    setFontSizeState(px);
    writeStorage(FONT_SIZE_STORAGE_KEY, String(px));
  }, []);

  const value = React.useMemo(
    () => ({ fontFamily, setFontFamily, fontSize, setFontSize }),
    [fontFamily, setFontFamily, fontSize, setFontSize]
  );

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

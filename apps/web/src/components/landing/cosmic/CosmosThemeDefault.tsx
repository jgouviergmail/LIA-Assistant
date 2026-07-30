'use client';

/**
 * Dark-first for the cosmos preview (owner arbitration): when the visitor has
 * NO stored theme preference, the public cosmos page defaults to dark. An
 * explicit choice (the header toggle) always wins — this effect only fills
 * the absence. The pre-paint half lives in the page's inline script (FOUC);
 * this half persists the default through next-themes so hydration agrees.
 */

import { useEffect } from 'react';
import { useTheme } from 'next-themes';

/** next-themes default storage key (ThemeProvider uses the default). */
const THEME_STORAGE_KEY = 'theme';

export function CosmosThemeDefault() {
  const { setTheme } = useTheme();

  useEffect(() => {
    try {
      if (window.localStorage.getItem(THEME_STORAGE_KEY) === null) {
        setTheme('dark');
      }
    } catch {
      // Storage unavailable (privacy mode): leave the provider's default.
    }
  }, [setTheme]);

  return null;
}

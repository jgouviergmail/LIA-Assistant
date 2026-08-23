'use client';

import * as React from 'react';

import {
  COLOR_THEME_STORAGE_KEY,
  DEFAULT_COLOR_THEME,
  type ColorThemeName,
  isColorThemeName,
} from '@/lib/color-themes';

// Types for theme context
type ThemeName = ColorThemeName;

interface ThemeContextValue {
  colorTheme: ThemeName;
  setColorTheme: (theme: ThemeName) => void;
}

const ThemeContext = React.createContext<ThemeContextValue | undefined>(undefined);

// Shared with the blocking anti-FOUC script (`ThemeInitScript`), which must
// apply the very same attribute before the first paint.
const STORAGE_KEY = COLOR_THEME_STORAGE_KEY;
const DEFAULT_THEME: ThemeName = DEFAULT_COLOR_THEME;

export function ColorThemeProvider({ children }: { children: React.ReactNode }) {
  const [colorTheme, setColorThemeState] = React.useState<ThemeName>(DEFAULT_THEME);
  const [mounted, setMounted] = React.useState(false);

  // Load theme from localStorage on mount
  React.useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isColorThemeName(stored)) {
      setColorThemeState(stored);
    }
    setMounted(true);
  }, []);

  // Apply data-theme to the html element
  React.useEffect(() => {
    if (!mounted) return;

    const html = document.documentElement;

    // Remove all old data-theme attributes
    html.removeAttribute('data-theme');

    // Apply the new theme (except for default)
    if (colorTheme !== 'default') {
      html.setAttribute('data-theme', colorTheme);
    }
  }, [colorTheme, mounted]);

  const setColorTheme = React.useCallback((theme: ThemeName) => {
    setColorThemeState(theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }, []);

  const value = React.useMemo(() => ({ colorTheme, setColorTheme }), [colorTheme, setColorTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useColorTheme() {
  const context = React.useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useColorTheme must be used within a ColorThemeProvider');
  }
  return context;
}

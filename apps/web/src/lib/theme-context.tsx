'use client';

import * as React from 'react';

// Types for theme context
type ThemeName = 'default' | 'ocean' | 'forest' | 'sunset' | 'slate';

interface ThemeContextValue {
  colorTheme: ThemeName;
  setColorTheme: (theme: ThemeName) => void;
}

const ThemeContext = React.createContext<ThemeContextValue | undefined>(undefined);

const STORAGE_KEY = 'color-theme';
const DEFAULT_THEME: ThemeName = 'default';

export function ColorThemeProvider({ children }: { children: React.ReactNode }) {
  const [colorTheme, setColorThemeState] = React.useState<ThemeName>(DEFAULT_THEME);
  const [mounted, setMounted] = React.useState(false);

  // Load theme from localStorage on mount
  React.useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as ThemeName | null;
    if (stored && ['default', 'ocean', 'forest', 'sunset', 'slate'].includes(stored)) {
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

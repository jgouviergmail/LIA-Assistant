'use client';

import { useContext } from 'react';
import { ThemePreferencesContext, type ThemePreferences } from '@/lib/theme-preferences';

export type UseThemeMode = ThemePreferences;

/** All consumers share the provider's single clock and serialized write queue. */
export function useThemeMode(): UseThemeMode {
  const context = useContext(ThemePreferencesContext);
  if (!context) throw new Error('useThemeMode requires ThemeModeProvider');
  return context;
}

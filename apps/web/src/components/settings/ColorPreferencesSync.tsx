'use client';

import { useEffect, useRef } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { isColorThemeName } from '@/lib/color-themes';
import { useColorTheme } from '@/lib/theme-context';

/** The account colour reaches every authenticated page through its existing owner. */
export function ColorPreferencesSync() {
  const { user } = useAuth();
  const { colorTheme, setColorTheme } = useColorTheme();
  const applied = useRef<{ id: string | undefined; value: string | undefined } | null>(null);
  const ownerId = user?.id;
  const accountTheme = user?.color_theme;
  useEffect(() => {
    if (applied.current?.id === ownerId && applied.current?.value === accountTheme) return;
    applied.current = { id: ownerId, value: accountTheme };
    if (isColorThemeName(accountTheme) && accountTheme !== colorTheme) setColorTheme(accountTheme);
  }, [ownerId, accountTheme, colorTheme, setColorTheme]);
  return null;
}

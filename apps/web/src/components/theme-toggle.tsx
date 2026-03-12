'use client';

import { useState, useEffect } from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/hooks/useAuth';
import { useApiMutation } from '@/hooks/useApiMutation';
import type { User } from '@/lib/auth';

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const { t } = useTranslation();
  const [mounted, setMounted] = useState(false);
  const { user, refreshUser } = useAuth();

  // API mutation to save theme preference
  const { mutate: updateTheme } = useApiMutation<{ theme: string }, User>({
    method: 'PATCH',
    componentName: 'ThemeToggle',
    onSuccess: async () => {
      await refreshUser?.();
    },
  });

  // Sync theme from user on mount (if user has a saved theme)
  useEffect(() => {
    if (user?.theme && user.theme !== 'system' && user.theme !== theme) {
      setTheme(user.theme);
    }
  }, [user?.theme, theme, setTheme]);

  // Avoid flash during loading
  useEffect(() => {
    setMounted(true);
  }, []);

  const handleThemeChange = async () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);

    // Save to backend if user is authenticated
    if (user?.id) {
      await updateTheme(`/users/${user.id}`, { theme: newTheme });
    }
  };

  if (!mounted) {
    return (
      <Button variant="ghost" size="sm" className="w-11 h-11 px-0">
        <Sun className="h-[1.2rem] w-[1.2rem]" />
        <span className="sr-only">{t('theme.toggle')}</span>
      </Button>
    );
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      className="w-11 h-11 px-0"
      onClick={handleThemeChange}
      aria-label={t('theme.toggle')}
    >
      {theme === 'dark' ? (
        <Sun className="h-[1.2rem] w-[1.2rem] transition-all" />
      ) : (
        <Moon className="h-[1.2rem] w-[1.2rem] transition-all" />
      )}
      <span className="sr-only">{t('theme.toggle')}</span>
    </Button>
  );
}

'use client';

import { useState, useEffect } from 'react';
import { useTheme } from 'next-themes';
import { useColorTheme } from '@/lib/theme-context';
import { Check, Palette } from 'lucide-react';
import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useAuth } from '@/hooks/useAuth';
import { useApiMutation } from '@/hooks/useApiMutation';
import type { User } from '@/lib/auth';

// Available themes definition (labels and descriptions come from translations)
// Colors aligned with globals.css for an accurate preview
const THEMES = [
  {
    name: 'default' as const,
    // Professional Blue - slate blue
    primaryColor: 'oklch(55% 0.13 240)',
    darkPrimaryColor: 'oklch(68% 0.20 250)',
  },
  {
    name: 'ocean' as const,
    // Deep Teal - sophisticated and calming
    primaryColor: 'oklch(58% 0.14 185)',
    darkPrimaryColor: 'oklch(72% 0.16 185)',
  },
  {
    name: 'forest' as const,
    // Sage Green - modern and organic
    primaryColor: 'oklch(52% 0.10 145)',
    darkPrimaryColor: 'oklch(68% 0.14 145)',
  },
  {
    name: 'sunset' as const,
    // Rose - elegant and warm
    primaryColor: 'oklch(58% 0.12 10)',
    darkPrimaryColor: 'oklch(72% 0.15 10)',
  },
  {
    name: 'slate' as const,
    // Lavender - refined and calm
    primaryColor: 'oklch(55% 0.12 290)',
    darkPrimaryColor: 'oklch(72% 0.14 290)',
  },
] as const;

interface ThemeSelectorProps {
  lng: Language;
  /**
   * If true, wraps in SettingsSection (collapsible)
   * If false, renders only the content
   */
  collapsible?: boolean;
}

export function ThemeSelector({ lng, collapsible = true }: ThemeSelectorProps) {
  const { resolvedTheme } = useTheme();
  const { colorTheme, setColorTheme } = useColorTheme();
  const [mounted, setMounted] = useState(false);
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();

  // API mutation to save theme preference
  const { mutate: updateTheme } = useApiMutation<{ color_theme: string }, User>({
    method: 'PATCH',
    componentName: 'ThemeSelector',
    onSuccess: async () => {
      await refreshUser?.();
    },
  });

  // Sync theme from user on mount (if user has a saved theme)
  // Intentionally excludes colorTheme/setColorTheme to avoid re-triggering on local changes
  // This is a one-way sync: user preference → local state (not bidirectional)
  useEffect(() => {
    if (user?.color_theme && user.color_theme !== colorTheme) {
      setColorTheme(user.color_theme as (typeof THEMES)[number]['name']);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.color_theme]);

  // Avoid flash during loading
  useEffect(() => {
    setMounted(true);
  }, []);

  const isDarkMode = resolvedTheme === 'dark';

  const handleThemeChange = async (themeName: (typeof THEMES)[number]['name']) => {
    // Update local state immediately for responsive UI
    setColorTheme(themeName);

    // Save to backend if user is authenticated
    if (user?.id) {
      await updateTheme(`/users/${user.id}`, { color_theme: themeName });
    }
  };

  const content = (
    <div className="space-y-4">
      {!mounted ? (
        <div className="text-sm text-muted-foreground">{t('common.loading')}</div>
      ) : (
        <>
          <div className="grid gap-3">
            {THEMES.map(themeOption => {
              const isSelected = colorTheme === themeOption.name;
              const previewColor = isDarkMode
                ? themeOption.darkPrimaryColor
                : themeOption.primaryColor;

              return (
                <button
                  key={themeOption.name}
                  type="button"
                  onClick={() => handleThemeChange(themeOption.name)}
                  className={`
                    relative flex items-start gap-3 rounded-lg border-2 p-4 text-left transition-all
                    hover:bg-accent hover:shadow-sm
                    ${
                      isSelected ? 'border-primary bg-primary/5 shadow-sm' : 'border-border bg-card'
                    }
                  `}
                  aria-label={t(`settings.theme.themes.${themeOption.name}.label`)}
                >
                  {/* Selection indicator */}
                  <div
                    className={`
                      mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors
                      ${
                        isSelected
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-muted-foreground/30'
                      }
                    `}
                  >
                    {isSelected && <Check className="h-3 w-3" strokeWidth={3} />}
                  </div>

                  {/* Color preview */}
                  <div
                    className="mt-0.5 h-5 w-5 shrink-0 rounded-full border border-border shadow-sm"
                    style={{ backgroundColor: previewColor }}
                    aria-hidden="true"
                  />

                  {/* Theme details */}
                  <div className="flex-1 space-y-1">
                    <Label
                      htmlFor={themeOption.name}
                      className={`cursor-pointer text-sm font-medium ${
                        isSelected ? 'text-primary' : 'text-foreground'
                      }`}
                    >
                      {t(`settings.theme.themes.${themeOption.name}.label`)}
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      {t(`settings.theme.themes.${themeOption.name}.description`)}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>

          <InfoBox>
            <p className="text-xs text-muted-foreground">{t('settings.theme.dark_mode_tip')}</p>
          </InfoBox>
        </>
      )}
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="theme"
      title={t('settings.theme.title')}
      description={t('settings.theme.description')}
      icon={Palette}
    >
      {content}
    </SettingsSection>
  );
}

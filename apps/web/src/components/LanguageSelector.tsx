/**
 * Language Selector Component
 *
 * Dropdown menu to switch between supported languages.
 * Changes URL path to reflect selected language and syncs to database.
 */

'use client';

import { usePathname, useRouter } from 'next/navigation';
import { Globe } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import {
  languages,
  languageNames,
  languageFlags,
  setLocaleCookie,
  type Language,
} from '@/i18n/settings';
import { switchLanguageInPath } from '@/utils/i18n-path-utils';
import { useAuth } from '@/hooks/useAuth';
import { frontendToBackendLocale } from '@/utils/locale-mapping';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';

interface LanguageSelectorProps {
  currentLocale: Language;
}

/**
 * Language Selector
 *
 * Displays current language and allows switching between all supported languages.
 * Updates the URL path to reflect the new language and syncs to database.
 *
 * @param props - Component props
 */
export function LanguageSelector({ currentLocale }: LanguageSelectorProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, refreshUser } = useAuth();
  const { t } = useTranslation();

  const handleLanguageChange = async (newLang: Language) => {
    if (newLang === currentLocale) return;

    // Convert frontend locale to backend language code
    const backendLanguage = frontendToBackendLocale(newLang);

    // Update language in database if user is authenticated
    if (user?.id) {
      try {
        await apiClient.patch(`/users/${user.id}`, { language: backendLanguage });

        // Refresh user context to get updated language
        await refreshUser?.();

        logger.info('Language updated via header selector', {
          component: 'LanguageSelector',
          userId: user.id,
          newLanguage: backendLanguage,
          frontendLocale: newLang,
        });
      } catch (error) {
        logger.error('Failed to update language in database', error as Error, {
          component: 'LanguageSelector',
          userId: user.id,
          newLanguage: backendLanguage,
        });
        // Continue with URL change even if API call fails
      }
    }

    // Update locale cookie for next-i18n-router
    setLocaleCookie(newLang);

    // Navigate to the same page with new language
    router.push(switchLanguageInPath(pathname, newLang));
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          // `min-w-11` because below `xl` the label collapses to a single flag
          // glyph: the height was already 44 px, the WIDTH fell to 39 and the
          // target failed on a phone (measured 2026-08-01 at 390 px).
          className="gap-2 h-11 min-w-11 px-3 max-[380px]:gap-1 max-[380px]:h-9 max-[380px]:min-w-9 max-[380px]:px-2"
          // Below `xl` only the flag renders (the header row cannot fit the
          // language name next to the nav), and a flag emoji is not an
          // accessible name — carry it explicitly, with the current value.
          aria-label={t('settings.language.selector_label', {
            name: languageNames[currentLocale].native,
          })}
        >
          <Globe className="hidden xl:block h-4 w-4" />
          <span className="hidden xl:inline">{languageNames[currentLocale].native}</span>
          <span className="xl:hidden">{languageFlags[currentLocale]}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {languages.map(lang => (
          <DropdownMenuItem
            key={lang}
            onClick={() => handleLanguageChange(lang)}
            className={currentLocale === lang ? 'bg-accent' : ''}
          >
            <span className="mr-2">{languageFlags[lang]}</span>
            <span className="flex-1">{languageNames[lang].native}</span>
            {currentLocale === lang && (
              <span className="ml-2 text-xs text-muted-foreground">✓</span>
            )}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

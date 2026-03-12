'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApiMutation } from '@/hooks/useApiMutation';
import { Check, Languages, Info } from 'lucide-react';
import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import {
  type Language,
  languages,
  languageNames,
  languageFlags,
  setLocaleCookie,
} from '@/i18n/settings';
import { switchLanguageInPath } from '@/utils/i18n-path-utils';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';
import { type User } from '@/lib/auth';
import { useRouter } from 'next/navigation';
import {
  frontendToBackendLocale,
  backendToFrontendLocale,
  getBrowserLanguageForBackend,
} from '@/utils/locale-mapping';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';

export function LanguageSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { user, refreshUser } = useAuth();
  const { t } = useTranslation(lng);
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [browserLanguage, setBrowserLanguage] = useState<string | null>(null);
  // Initialize with lng from URL to avoid default FR
  const [selectedLanguage, setSelectedLanguage] = useState<Language>(lng);

  // Detect browser language on mount (once)
  useEffect(() => {
    setMounted(true);
    const detected = getBrowserLanguageForBackend();
    setBrowserLanguage(detected);

    logger.info('LanguageSettings mounted', {
      component: 'LanguageSettings',
      userId: user?.id,
      userLanguage: user?.language,
      browserLanguage: detected,
      urlLanguage: lng,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Intentionally run only on mount - user/lng captured in closure for logging only

  // Sync selectedLanguage with lng prop (URL) when it changes
  useEffect(() => {
    if (lng !== selectedLanguage) {
      logger.info('Syncing language from URL', {
        component: 'LanguageSettings',
        currentSelected: selectedLanguage,
        urlLanguage: lng,
      });
      setSelectedLanguage(lng);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lng]); // Only react to lng changes, not selectedLanguage (to avoid infinite loop)

  // Sync selectedLanguage with user.language from database, but only if different
  useEffect(() => {
    if (user?.language) {
      const frontendLocale = backendToFrontendLocale(user.language);
      // Only update if it's different from current selection to avoid infinite loop
      if (frontendLocale !== selectedLanguage) {
        logger.info('Syncing language from database', {
          component: 'LanguageSettings',
          currentSelected: selectedLanguage,
          dbLanguage: frontendLocale,
        });
        setSelectedLanguage(frontendLocale);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.language]); // Only depend on user.language, not selectedLanguage (to avoid loop)

  // Mutation hook for updating language
  const { mutate: updateLanguage, loading: updating } = useApiMutation<{ language: string }, User>({
    method: 'PATCH',
    componentName: 'LanguageSettings',
    onSuccess: async updatedUser => {
      toast.success(t('settings.language.update_success'));

      // Show info about persisted preference
      toast.info(t('settings.language.persistence_info'), {
        duration: 5000,
      });

      // Refresh user context
      await refreshUser?.();

      if (updatedUser.language) {
        const frontendLocale = backendToFrontendLocale(updatedUser.language);
        setSelectedLanguage(frontendLocale);

        // Update locale cookie for next-i18n-router
        setLocaleCookie(frontendLocale);

        // Navigate to the same page with new language
        const pathname = window.location.pathname;
        const newPathname = switchLanguageInPath(pathname, frontendLocale);

        // Only navigate if the path changed
        if (newPathname !== pathname) {
          router.push(newPathname);
        }
      }

      logger.info('Language updated successfully', {
        component: 'LanguageSettings',
        old_language: user?.language,
        new_language: updatedUser.language,
      });
    },
    onError: error => {
      toast.error(t('settings.language.update_error'));
      logger.error('Failed to update language', error, { component: 'LanguageSettings' });
    },
  });

  const handleLanguageChange = async (frontendLang: Language) => {
    if (!user?.id) {
      logger.warn('Cannot update language: no user ID', { component: 'LanguageSettings' });
      return;
    }

    // Don't update if already the same language
    if (frontendLang === selectedLanguage) {
      logger.info('Language already set to this value', {
        component: 'LanguageSettings',
        language: frontendLang,
      });
      return;
    }

    // Convert frontend locale to backend language code
    const backendLanguage = frontendToBackendLocale(frontendLang);

    logger.info('Updating language', {
      component: 'LanguageSettings',
      userId: user.id,
      oldLanguage: user.language,
      newLanguage: backendLanguage,
      frontendLocale: frontendLang,
    });

    // Update selected language immediately for UI feedback
    setSelectedLanguage(frontendLang);

    // Call API to update in database
    await updateLanguage(`/users/${user.id}`, { language: backendLanguage });
  };

  if (!user) return null;

  // Use selectedLanguage (initialized from URL lng), no fallback to 'fr'
  const currentLanguage = selectedLanguage;
  const browserLanguageFrontend = browserLanguage ? backendToFrontendLocale(browserLanguage) : null;
  const isBrowserDetected = browserLanguageFrontend === currentLanguage;

  const content = (
    <div className="space-y-4">
      {!mounted ? (
        <div className="text-sm text-muted-foreground">{t('common.loading')}</div>
      ) : (
        <>
          {/* Current language display */}
          {currentLanguage && (
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 space-y-2">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 space-y-1">
                  <Label className="text-sm font-medium">{t('settings.language.current')}</Label>
                  <p className="text-base font-semibold text-primary flex items-center gap-2">
                    <span>{languageFlags[currentLanguage]}</span>
                    <span>{languageNames[currentLanguage].native}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {languageNames[currentLanguage].english}
                  </p>
                </div>
                {isBrowserDetected && (
                  <div className="rounded-md bg-green-500/10 px-2 py-1 text-xs text-green-700 dark:text-green-400">
                    {t('settings.language.browser_match')}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Browser language suggestion */}
          {browserLanguageFrontend && browserLanguageFrontend !== currentLanguage && (
            <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3 space-y-2">
              <div className="flex items-start gap-2">
                <Info className="h-4 w-4 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
                <div className="flex-1 space-y-2">
                  <p className="text-sm text-blue-900 dark:text-blue-100">
                    {t('settings.language.browser_suggestion')}
                  </p>
                  <button
                    type="button"
                    onClick={() => handleLanguageChange(browserLanguageFrontend)}
                    disabled={updating}
                    className="text-sm font-medium text-blue-700 dark:text-blue-300 hover:underline disabled:opacity-50"
                  >
                    {t('settings.language.use_browser')} ({languageFlags[browserLanguageFrontend]}{' '}
                    {languageNames[browserLanguageFrontend].native})
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Language list */}
          <div className="space-y-2">
            <Label>{t('settings.language.available_languages')}</Label>
            <div className="grid gap-2">
              {languages.map(language => {
                const isSelected = language === currentLanguage;
                const { native, english } = languageNames[language];
                const flag = languageFlags[language];

                return (
                  <button
                    key={language}
                    type="button"
                    onClick={() => handleLanguageChange(language)}
                    disabled={updating || isSelected}
                    className={`
                      relative flex items-start gap-3 rounded-lg border-2 p-3 text-left transition-all
                      hover:bg-accent hover:shadow-sm
                      disabled:opacity-50 disabled:cursor-not-allowed
                      ${
                        isSelected
                          ? 'border-primary bg-primary/5 shadow-sm'
                          : 'border-border bg-card'
                      }
                    `}
                    aria-label={`Select ${native}`}
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

                    {/* Language details */}
                    <div className="flex-1 space-y-0.5">
                      <Label
                        className={`cursor-pointer text-sm font-medium flex items-center gap-2 ${
                          isSelected ? 'text-primary' : 'text-foreground'
                        }`}
                      >
                        <span className="text-base">{flag}</span>
                        <span>{native}</span>
                      </Label>
                      <p className="text-xs text-muted-foreground">{english}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Info note */}
          <InfoBox>
            <p className="text-xs text-muted-foreground">{t('settings.language.info_note')}</p>
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
      value="language"
      title={t('settings.language.title')}
      description={t('settings.language.description')}
      icon={Languages}
    >
      {content}
    </SettingsSection>
  );
}

'use client';

import { useState, useEffect } from 'react';
import { useFontFamily, type FontFamilyName } from '@/lib/font-context';
import { FONT_DEFINITIONS, isValidFontFamily } from '@/constants/fonts';
import { Check, Type } from 'lucide-react';
import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useAuth } from '@/hooks/useAuth';
import { useApiMutation } from '@/hooks/useApiMutation';
import type { User } from '@/lib/auth';

interface FontSettingsProps {
  lng: Language;
  collapsible?: boolean;
}

export function FontSettings({ lng, collapsible = true }: FontSettingsProps) {
  const { fontFamily, setFontFamily } = useFontFamily();
  const [mounted, setMounted] = useState(false);
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();

  // API mutation to save font preference
  const { mutate: updateFont } = useApiMutation<{ font_family: string }, User>({
    method: 'PATCH',
    componentName: 'FontSettings',
    onSuccess: async () => {
      await refreshUser?.();
    },
  });

  // Sync font from user on mount
  useEffect(() => {
    if (
      user?.font_family &&
      isValidFontFamily(user.font_family) &&
      user.font_family !== fontFamily
    ) {
      setFontFamily(user.font_family);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.font_family]);

  // Avoid flash on load
  useEffect(() => {
    setMounted(true);
  }, []);

  const handleFontChange = async (fontName: FontFamilyName) => {
    // Update local state immediately for responsive UI
    setFontFamily(fontName);

    // Save to backend if user is authenticated
    if (user?.id) {
      await updateFont(`/users/${user.id}`, { font_family: fontName });
    }
  };

  const content = (
    <div className="space-y-4">
      {!mounted ? (
        <div className="text-sm text-muted-foreground">{t('common.loading')}</div>
      ) : (
        <>
          <div className="grid gap-3">
            {FONT_DEFINITIONS.map(fontOption => {
              const isSelected = fontFamily === fontOption.name;

              return (
                <button
                  key={fontOption.name}
                  type="button"
                  onClick={() => handleFontChange(fontOption.name)}
                  className={`
                    relative flex items-start gap-3 rounded-lg border-2 p-4 text-left transition-all
                    hover:bg-accent hover:shadow-sm
                    ${isSelected ? 'border-primary bg-primary/5 shadow-sm' : 'border-border bg-card'}
                  `}
                  aria-label={t(`settings.font.fonts.${fontOption.name}.label`)}
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

                  {/* Font preview "Aa" */}
                  <div
                    className="mt-0.5 flex h-6 w-8 shrink-0 items-center justify-center text-base font-medium text-foreground"
                    style={{ fontFamily: fontOption.fontFamily }}
                    aria-hidden="true"
                  >
                    Aa
                  </div>

                  {/* Font details */}
                  <div className="flex-1 space-y-1">
                    <Label
                      className={`cursor-pointer text-sm font-medium ${
                        isSelected ? 'text-primary' : 'text-foreground'
                      }`}
                    >
                      {t(`settings.font.fonts.${fontOption.name}.label`)}
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      {t(`settings.font.fonts.${fontOption.name}.description`)}
                    </p>
                    {/* Sample text in the font */}
                    <p
                      className="text-sm text-foreground/80"
                      style={{ fontFamily: fontOption.fontFamily }}
                    >
                      {t('settings.font.sample_text')}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>

          <InfoBox>
            <p className="text-xs text-muted-foreground">{t('settings.font.info_note')}</p>
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
      value="font"
      title={t('settings.font.title')}
      description={t('settings.font.description')}
      icon={Type}
    >
      {content}
    </SettingsSection>
  );
}

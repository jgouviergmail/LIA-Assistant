'use client';

import { Check, Sparkles } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { usePersonality } from '@/hooks/usePersonality';
import { usePsycheStore } from '@/stores/psycheStore';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import type { PsycheState } from '@/types/psyche';
import type { BaseSettingsProps } from '@/types/settings';

export function PersonalitySettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { personalities, currentPersonality, loading, updating, updatePersonality } =
    usePersonality();

  const handlePersonalityChange = async (personalityId: string | null) => {
    try {
      await updatePersonality(personalityId);
      toast.success(t('personality.update_success'));
      // Fetch fresh psyche state (Big Five traits change with personality)
      try {
        const freshState = await apiClient.get<PsycheState>('/psyche/state');
        usePsycheStore.getState().updateFromFullState(freshState);
      } catch {
        // Best-effort — psyche state will refresh on next page load
      }
    } catch {
      toast.error(t('personality.update_error'));
    }
  };

  const content = (
    <div className="space-y-4">
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoadingSpinner size="default" />
          {t('common.loading')}
        </div>
      ) : (
        <>
          <div className="grid gap-3">
            {personalities.map(personality => {
              const isSelected =
                currentPersonality?.id === personality.id ||
                (!currentPersonality && personality.is_default);

              return (
                <button
                  key={personality.id}
                  type="button"
                  onClick={() => handlePersonalityChange(personality.id)}
                  disabled={updating}
                  className={`
                    relative flex items-start gap-3 rounded-lg border-2 p-4 text-left transition-all
                    hover:bg-accent hover:shadow-sm
                    disabled:opacity-50 disabled:cursor-not-allowed
                    ${
                      isSelected ? 'border-primary bg-primary/5 shadow-sm' : 'border-border bg-card'
                    }
                  `}
                  aria-label={personality.title}
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

                  {/* Emoji */}
                  <div
                    className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center text-xl"
                    aria-hidden="true"
                  >
                    {personality.emoji}
                  </div>

                  {/* Personality details */}
                  <div className="flex-1 space-y-1">
                    <Label
                      className={`cursor-pointer text-sm font-medium ${
                        isSelected ? 'text-primary' : 'text-foreground'
                      }`}
                    >
                      {personality.title}
                      {personality.is_default && (
                        <span className="ml-2 text-xs font-normal text-muted-foreground">
                          ({t('personality.default')})
                        </span>
                      )}
                    </Label>
                    <p className="text-xs text-muted-foreground">{personality.description}</p>
                  </div>

                  {/* Loading indicator when updating */}
                  {updating && isSelected && <LoadingSpinner size="default" />}
                </button>
              );
            })}
          </div>

          <InfoBox>
            <p className="text-xs text-muted-foreground">{t('personality.change_hint')}</p>
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
      value="personality"
      title={t('personality.settings.title')}
      description={t('personality.settings.description')}
      icon={Sparkles}
    >
      {content}
    </SettingsSection>
  );
}

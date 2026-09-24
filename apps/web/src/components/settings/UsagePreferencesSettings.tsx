'use client';

import { useState } from 'react';
import { MessageSquare, MessagesSquare, UserCog } from 'lucide-react';
import { toast } from 'sonner';

import { SettingsSection } from '@/components/settings/SettingsSection';
import { InfoBox } from '@/components/ui/info-box';
import { useAuth } from '@/hooks/useAuth';
import { useTranslation } from '@/i18n/client';
import apiClient from '@/lib/api-client';
import { EXCHANGE_RHYTHMS, type ExchangeRhythm } from '@/lib/exchange-rhythm';
import { cn } from '@/lib/utils';
import type { BaseSettingsProps } from '@/types/settings';

const RHYTHM_ICONS: Readonly<Record<ExchangeRhythm, typeof MessagesSquare>> = {
  frequent: MessagesSquare,
  occasional: MessageSquare,
};

const PREFIX = 'settings.usage_preferences.exchange_rhythm';

/**
 * Usage preferences — how LIA adapts to the way a person uses it (ADR-311).
 *
 * Its first setting is the exchange rhythm. Frequent exchanges bind every tool
 * and shape each ReAct turn's prompt so the next turn reads it back from the
 * provider's cache; occasional exchanges pick the tools each question needs.
 * The choice travels through the generic profile update, and the API publishes
 * the EFFECTIVE rhythm (the choice, else the instance default), so one option
 * is always checked. Native radios give the group semantics and the arrow-key
 * navigation; the fieldset disables both options while a choice is saved.
 */
export function UsagePreferencesSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const [saving, setSaving] = useState(false);
  const current = user?.exchange_rhythm;

  const choose = async (rhythm: ExchangeRhythm) => {
    if (!user || saving || rhythm === current) return;

    setSaving(true);
    try {
      await apiClient.patch(`/users/${user.id}`, { exchange_rhythm: rhythm });
      await refreshUser();
      toast.success(t(`${PREFIX}.options.${rhythm}.selected`));
    } catch {
      toast.error(t('common.error'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <SettingsSection
      value="usage-preferences"
      title={t('settings.usage_preferences.title')}
      description={t('settings.usage_preferences.description')}
      icon={UserCog}
    >
      <div className="space-y-4">
        <fieldset disabled={saving || !user} aria-describedby="exchange-rhythm-hint">
          <legend className="mb-1 text-sm font-medium text-foreground">
            {t(`${PREFIX}.legend`)}
          </legend>
          <p id="exchange-rhythm-hint" className="mb-3 text-xs text-muted-foreground">
            {t(`${PREFIX}.hint`)}
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {EXCHANGE_RHYTHMS.map(rhythm => {
              const Icon = RHYTHM_ICONS[rhythm];
              const selected = current === rhythm;
              return (
                <label
                  key={rhythm}
                  className={cn(
                    'flex cursor-pointer flex-col gap-1.5 rounded-lg border-2 p-3 transition-all hover:bg-accent',
                    'has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background',
                    'has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60',
                    selected ? 'border-primary bg-primary/5' : 'border-border bg-card'
                  )}
                >
                  <input
                    type="radio"
                    name="exchange-rhythm"
                    value={rhythm}
                    checked={selected}
                    onChange={() => void choose(rhythm)}
                    aria-labelledby={`exchange-rhythm-${rhythm}-label`}
                    aria-describedby={`exchange-rhythm-${rhythm}-description`}
                    className="sr-only"
                  />
                  <span className="flex items-center gap-2">
                    <Icon
                      className={cn('h-4 w-4', selected ? 'text-primary' : 'text-muted-foreground')}
                      aria-hidden="true"
                    />
                    <span
                      id={`exchange-rhythm-${rhythm}-label`}
                      className={cn(
                        'text-sm font-medium',
                        selected ? 'text-primary' : 'text-foreground'
                      )}
                    >
                      {t(`${PREFIX}.options.${rhythm}.label`)}
                    </span>
                  </span>
                  <span
                    id={`exchange-rhythm-${rhythm}-description`}
                    className="text-xs text-muted-foreground"
                  >
                    {t(`${PREFIX}.options.${rhythm}.description`)}
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <InfoBox>
          <p className="text-xs text-muted-foreground">{t(`${PREFIX}.fallback`)}</p>
        </InfoBox>
      </div>
    </SettingsSection>
  );
}

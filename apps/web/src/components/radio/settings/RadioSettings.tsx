'use client';

/**
 * RadioSettings — what the listener's radio says, and how (ADR-324).
 *
 * Every choice offered comes from `GET /radio/options`, published because the
 * API enforces it; every change is saved at once, optimistically and in order
 * (`useRadioSettings`). A save never unmounts the form — a first load shows
 * placeholders, a save only marks the form busy — so a keyboard user keeps
 * their place.
 */
import { Radio } from 'lucide-react';
import { toast } from 'sonner';

import { SettingsSection } from '@/components/settings/SettingsSection';
import { Skeleton } from '@/components/ui/skeleton';
import { useRadioSettings } from '@/hooks/useRadioSettings';
import { useTranslation } from '@/i18n/client';
import { sayRefusal } from '@/lib/radio/errors';
import type { RadioOptions, RadioPreferences } from '@/lib/radio/types';
import type { BaseSettingsProps } from '@/types/settings';

import { RadioBudgetFields } from './RadioBudgetFields';
import { RadioListeningFields } from './RadioListeningFields';
import { RadioProgrammeFields } from './RadioProgrammeFields';
import { RadioSourceFields } from './RadioSourceFields';
import { RadioSourcesFields } from './RadioSourcesFields';
import { RadioVoiceFields } from './RadioVoiceFields';

export function RadioSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { options, preferences, loading, saving, save } = useRadioSettings();
  const change = async (next: RadioPreferences) => {
    const saved = await save(next);
    if (!saved.ok) toast.error(sayRefusal(t, saved.refusal, 'radio.settings.save_failed'));
  };
  return (
    <SettingsSection
      value="radio"
      icon={Radio}
      title={t('radio.settings.title')}
      description={t('radio.settings.description')}
    >
      <RadioSettingsBody
        lng={lng}
        loading={loading}
        saving={saving}
        options={options}
        preferences={preferences}
        onChange={change}
      />
    </SettingsSection>
  );
}

function RadioSettingsBody({
  lng,
  loading,
  saving,
  options,
  preferences,
  onChange,
}: {
  lng: BaseSettingsProps['lng'];
  loading: boolean;
  saving: boolean;
  options: RadioOptions | null;
  preferences: RadioPreferences | null;
  onChange: (next: RadioPreferences) => Promise<void>;
}) {
  const { t } = useTranslation(lng);
  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (options === null || preferences === null) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t('radio.settings.unavailable')}
      </p>
    );
  }
  const fields = {
    lng,
    options,
    preferences,
    onChange: (next: RadioPreferences) => void onChange(next),
  };
  return (
    <div className="space-y-3" aria-busy={saving}>
      <RadioProgrammeFields {...fields} />
      <RadioSourceFields {...fields} />
      <RadioSourcesFields
        lng={lng}
        options={options}
        preferences={preferences}
        onChange={onChange}
      />
      <RadioVoiceFields {...fields} />
      <RadioListeningFields {...fields} />
      <RadioBudgetFields lng={lng} />
    </div>
  );
}

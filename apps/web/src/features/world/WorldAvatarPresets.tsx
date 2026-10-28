'use client';
import { useId } from 'react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { AvatarAppearance } from './avatar-catalogue';
import { AVATAR_PRESETS, matchingAvatarPreset } from './avatar-presets';

export function WorldAvatarPresets({
  lng,
  appearance,
  onChange,
}: {
  lng: Language;
  appearance: AvatarAppearance;
  onChange(value: AvatarAppearance): void;
}) {
  const { t } = useTranslation(lng);
  const id = useId();
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {t('world.avatar.presets.label')}
      </label>
      <select
        id={id}
        aria-label={t('world.avatar.presets.label')}
        className="min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm"
        value={matchingAvatarPreset(appearance)?.id ?? 'custom'}
        onChange={event => {
          const selected = AVATAR_PRESETS.find(preset => preset.id === event.target.value);
          if (selected) onChange({ ...selected.appearance });
        }}
      >
        <option value="custom">{t('world.avatar.presets.custom')}</option>
        {(['masculine', 'feminine'] as const).map(group => (
          <optgroup key={group} label={t('world.avatar.presets.' + group)}>
            {AVATAR_PRESETS.filter(preset => preset.presentation === group).map(preset => (
              <option key={preset.id} value={preset.id}>
                {t(preset.titleKey)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <p className="text-xs text-muted-foreground">{t('world.avatar.presets.hint')}</p>
    </div>
  );
}

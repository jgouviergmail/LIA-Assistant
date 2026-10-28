'use client';
import { useId, useState } from 'react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { experiencePreferencesSchema, type ExperienceEdit } from './experience-protocol';
import type { WorldExperienceControl } from './useWorldExperiencePreferences';

export function WorldSeasonControls({
  lng,
  control,
  enabled,
}: {
  lng: Language;
  control: WorldExperienceControl;
  enabled: boolean;
}) {
  const { t } = useTranslation(lng);
  const id = useId();
  const [failed, setFailed] = useState(false);
  const view = control.experience;
  // A select keeps its focus while a write is pending: the guard, not a native
  // `disabled`, refuses the change (a disabled control drops focus to <body>).
  const blocked = !enabled || !view || view.needs_reset || control.saving;
  async function save(edit: ExperienceEdit) {
    if (blocked || !view) return;
    try {
      setFailed(!(await control.save({ expected_revision: view.preferences.revision, ...edit })));
    } catch {
      setFailed(true);
    }
  }
  return (
    <fieldset className="min-w-0 space-y-3 rounded-xl border p-3">
      <legend className="px-1 text-sm font-medium">{t('world.seasons.title')}</legend>
      <p className="text-xs text-muted-foreground">{t('world.seasons.hint')}</p>
      <label htmlFor={id + '-mode'} className="block text-sm">
        {t('world.seasons.mode')}
      </label>
      <select
        id={id + '-mode'}
        aria-label={t('world.seasons.mode')}
        aria-disabled={blocked}
        className="min-h-11 w-full rounded-xl border bg-background px-3 text-sm aria-disabled:opacity-60"
        value={view?.preferences.season_mode ?? 'calendar'}
        onChange={event => {
          const parsed = experiencePreferencesSchema.shape.season_mode.safeParse(
            event.target.value
          );
          if (parsed.success) void save({ season_mode: parsed.data });
        }}
      >
        {experiencePreferencesSchema.shape.season_mode.options.map(mode => (
          <option key={mode} value={mode}>
            {t('world.seasons.' + mode)}
          </option>
        ))}
      </select>
      <label htmlFor={id + '-hemisphere'} className="block text-sm">
        {t('world.seasons.hemisphere')}
      </label>
      <select
        id={id + '-hemisphere'}
        aria-label={t('world.seasons.hemisphere')}
        aria-disabled={blocked}
        className="min-h-11 w-full rounded-xl border bg-background px-3 text-sm aria-disabled:opacity-60"
        value={view?.preferences.hemisphere ?? 'north'}
        onChange={event => {
          const parsed = experiencePreferencesSchema.shape.hemisphere.safeParse(event.target.value);
          if (parsed.success) void save({ hemisphere: parsed.data });
        }}
      >
        {experiencePreferencesSchema.shape.hemisphere.options.map(hemisphere => (
          <option key={hemisphere} value={hemisphere}>
            {t('world.seasons.' + hemisphere)}
          </option>
        ))}
      </select>
      {failed && (
        <p role="status" className="text-sm text-destructive">
          {t('world.experience.failed')}
        </p>
      )}
    </fieldset>
  );
}

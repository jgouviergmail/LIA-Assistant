'use client';

import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { ThemePreferences } from '@/lib/theme-preferences';

const timeText = (minute: number) =>
  `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;
const minuteOf = (text: string) => {
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(text)) return null;
  const [hour, minute] = text.split(':').map(Number);
  return hour * 60 + minute;
};

/** Both boundaries are edited together, so swapping day/night never saves half a pair. */
export function ThemeScheduleEditor({
  lng,
  schedule,
  setSchedule,
  saving,
}: {
  lng: Language;
} & Pick<ThemePreferences, 'schedule' | 'setSchedule' | 'saving'>) {
  const { t } = useTranslation(lng);
  const source = `${schedule.lightStartMinute}/${schedule.darkStartMinute}/${schedule.timezone}`;
  const [draft, setDraft] = useState({
    source,
    light: timeText(schedule.lightStartMinute),
    dark: timeText(schedule.darkStartMinute),
  });
  // A changed server preference invalidates this editor; ordinary renders never
  // replace a partially typed time. Updating during render preserves the nodes/focus.
  if (source !== draft.source)
    setDraft({
      source,
      light: timeText(schedule.lightStartMinute),
      dark: timeText(schedule.darkStartMinute),
    });
  const light = minuteOf(draft.light);
  const dark = minuteOf(draft.dark);
  const invalid = light === null || dark === null || light === dark;
  return (
    <form
      className="space-y-3"
      onSubmit={event => {
        event.preventDefault();
        event.stopPropagation();
        if (!saving && light !== null && dark !== null && light !== dark)
          void setSchedule({ lightStartMinute: light, darkStartMinute: dark });
      }}
    >
      <p className="text-sm text-muted-foreground">
        {t('settings.theme.schedule_timezone', { timezone: schedule.timezone })}
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Input
          type="time"
          label={t('settings.theme.light_start')}
          value={draft.light}
          onChange={event => setDraft({ ...draft, light: event.target.value })}
        />
        <Input
          type="time"
          label={t('settings.theme.dark_start')}
          value={draft.dark}
          onChange={event => setDraft({ ...draft, dark: event.target.value })}
        />
      </div>
      {invalid && (
        <p role="alert" className="text-sm text-destructive">
          {t('settings.theme.schedule_invalid')}
        </p>
      )}
      <Button type="submit" aria-disabled={saving || invalid} isLoading={saving}>
        {t('common.save')}
      </Button>
    </form>
  );
}

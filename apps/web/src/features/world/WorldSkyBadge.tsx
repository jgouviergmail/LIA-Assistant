'use client';

import { memo, useMemo } from 'react';
import { CloudFog, CloudRain, Moon, Snowflake, Sun } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { Atmosphere } from './atmosphere';

export const WorldSkyBadge = memo(function WorldSkyBadge({
  lng,
  atmosphere,
}: {
  lng: Language;
  atmosphere: Atmosphere;
}) {
  const { t } = useTranslation(lng);
  const clock = useMemo(
    () =>
      atmosphere.time !== null && atmosphere.timezone
        ? new Intl.DateTimeFormat(lng, {
            timeZone: atmosphere.timezone,
            hour: '2-digit',
            minute: '2-digit',
          }).format(atmosphere.time)
        : null,
    [atmosphere.time, atmosphere.timezone, lng]
  );
  const date = useMemo(
    () =>
      atmosphere.time !== null && atmosphere.timezone
        ? new Intl.DateTimeFormat(lng, {
            timeZone: atmosphere.timezone,
            day: 'numeric',
            month: 'short',
          }).format(atmosphere.time)
        : null,
    [atmosphere.time, atmosphere.timezone, lng]
  );
  const WeatherIcon = {
    rain: CloudRain,
    snow: Snowflake,
    fog: CloudFog,
    neutral: atmosphere.phase === 'night' ? Moon : Sun,
  }[atmosphere.weather];
  return (
    <div
      className="world-sky-badge flex items-center gap-1.5 text-xs text-foreground/80"
      aria-label={t('world.atmosphere.private')}
    >
      <WeatherIcon className="size-3.5 shrink-0 text-primary" aria-hidden="true" />
      {clock && (
        <time className="tabular-nums" title={date ?? undefined}>
          {date && <span className="hidden md:inline">{date} · </span>}
          {clock}
        </time>
      )}
      <span className="truncate">{t('world.atmosphere.' + atmosphere.phase)}</span>
    </div>
  );
});

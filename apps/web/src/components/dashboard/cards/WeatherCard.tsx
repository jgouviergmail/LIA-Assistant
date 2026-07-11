'use client';

import {
  CloudDrizzle,
  CloudLightning,
  CloudRain,
  CloudSun,
  Droplets,
  Snowflake,
  Wind,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import type { ComponentType } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { BriefingCard } from '../BriefingCard';
import type {
  CardSection,
  DailyForecastItem,
  ForecastAlert,
  ForecastAlertKind,
  WeatherData,
} from '@/types/briefing';

type LucideIcon = ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;

const FORECAST_ALERT_ICON: Record<ForecastAlertKind, LucideIcon> = {
  rain: CloudRain,
  thunderstorm: CloudLightning,
  snow: Snowflake,
  drizzle: CloudDrizzle,
};

type SkyAnimation = 'rain' | 'snow' | 'sun' | null;

/**
 * Map the OpenWeatherMap main condition code ('Clear', 'Rain', 'Snow', …) to
 * the decorative hero animation. Unknown codes animate nothing.
 */
function skyAnimationFor(conditionCode: string): SkyAnimation {
  const code = conditionCode.toLowerCase();
  if (code.includes('rain') || code.includes('drizzle') || code.includes('thunder')) {
    return 'rain';
  }
  if (code.includes('snow')) return 'snow';
  if (code.includes('clear')) return 'sun';
  return null;
}

interface WeatherCardProps {
  section: CardSection<WeatherData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

export function WeatherCard({ section, isRefreshing, onRefresh, staggerIndex }: WeatherCardProps) {
  const router = useRouter();
  const { i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  return (
    <BriefingCard<WeatherData>
      titleKey="dashboard.briefing.cards.weather.title"
      icon={<CloudSun className="h-5 w-5" />}
      tone="sky"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.weather.empty"
      onErrorCta={() => router.push(`/${lng}/dashboard/settings?section=connectors`)}
      renderContent={data => <WeatherContent data={data} />}
      staggerIndex={staggerIndex}
      centerContent
    />
  );
}

function WeatherContent({ data }: { data: WeatherData }) {
  const { t } = useTranslation();
  const sky = skyAnimationFor(data.condition_code);
  const tempLabel = t('dashboard.briefing.cards.weather.temp', {
    value: Math.round(data.temperature_c),
  });
  const minMax =
    data.temperature_min_c !== null && data.temperature_max_c !== null
      ? `${Math.round(data.temperature_min_c)}° / ${Math.round(data.temperature_max_c)}°`
      : null;
  const popPct =
    data.precipitation_probability !== null
      ? Math.round(data.precipitation_probability * 100)
      : null;
  const windLabel =
    data.wind_speed_kmh !== null
      ? `${Math.round(data.wind_speed_kmh)} km/h${data.wind_direction_cardinal ? ` ${data.wind_direction_cardinal}` : ''}`
      : null;

  const showMetricsRow = windLabel !== null || popPct !== null || data.forecast_alert !== null;

  return (
    <div className="w-full flex flex-col items-center gap-2">
      {/* Hero: emoji + current temp + min/max — the emoji sky comes alive
          (falling drops/flakes, rotating sun halo) based on condition_code */}
      <div className="flex items-baseline justify-center gap-2">
        <span className="relative inline-flex" aria-hidden="true">
          {sky === 'sun' && <span className="lia-weather-rays" />}
          <span className="text-3xl leading-none">{data.icon_emoji}</span>
          {(sky === 'rain' || sky === 'snow') && (
            <span className="absolute inset-0">
              {[0, 1, 2].map(i => (
                <span
                  key={i}
                  className={cn('lia-weather-drop', sky === 'snow' && 'lia-weather-drop--snow')}
                  style={{ left: `${15 + i * 30}%`, animationDelay: `${i * 0.5}s` }}
                >
                  {sky === 'snow' ? '❄' : '💧'}
                </span>
              ))}
            </span>
          )}
        </span>
        <span className="text-3xl font-bold tabular-nums tracking-tight">{tempLabel}</span>
        {minMax && (
          <span className="text-xs text-muted-foreground tabular-nums ml-1">{minMax}</span>
        )}
      </div>

      {/* Description + city */}
      <p className="text-sm text-muted-foreground capitalize leading-snug">
        {data.description}
        {data.location_city && (
          <span className="text-muted-foreground/70"> · {data.location_city}</span>
        )}
      </p>

      {/* Metrics row: wind + rain probability + forecast alert (compact) */}
      {showMetricsRow && (
        <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {windLabel !== null && (
            <span className="inline-flex items-center gap-1">
              <Wind className="h-3 w-3" aria-hidden="true" />
              <span className="tabular-nums">{windLabel}</span>
            </span>
          )}
          {popPct !== null && (
            <span className="inline-flex items-center gap-1">
              <Droplets className="h-3 w-3" aria-hidden="true" />
              <span className="tabular-nums">{popPct}%</span>
            </span>
          )}
          {data.forecast_alert && <ForecastAlertBadge alert={data.forecast_alert} />}
        </div>
      )}

      {/* 5-day forecast strip */}
      {data.daily_forecast.length > 0 && (
        <div className="w-full pt-2 border-t border-border/30">
          <DailyForecastStrip days={data.daily_forecast} />
        </div>
      )}
    </div>
  );
}

function ForecastAlertBadge({ alert }: { alert: ForecastAlert }) {
  const { t } = useTranslation();
  const Icon = FORECAST_ALERT_ICON[alert.kind];
  const label = t('dashboard.briefing.cards.weather.forecast_alert', {
    context: alert.kind,
    time: alert.time,
  });
  return (
    <span className="inline-flex items-center gap-1 font-medium text-sky-700 dark:text-sky-300">
      <Icon className="h-3 w-3" aria-hidden={true} />
      <span className="tabular-nums">{label}</span>
    </span>
  );
}

function DailyForecastStrip({ days }: { days: DailyForecastItem[] }) {
  const { i18n } = useTranslation();
  const locale = i18n.language || 'fr';
  const weekdayFormatter = new Intl.DateTimeFormat(locale, { weekday: 'short' });

  return (
    <ul
      className="grid gap-1.5"
      style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}
      role="list"
    >
      {days.map(day => {
        // date_iso is 'YYYY-MM-DD' in user TZ; appending T00:00 keeps the
        // intended day stable when interpreted as local time.
        const localized = weekdayFormatter.format(new Date(`${day.date_iso}T00:00`));
        return (
          <li
            key={day.date_iso}
            className="flex flex-col items-center gap-0.5 text-center"
            title={`${day.date_iso} · ${day.condition_code}`}
          >
            <span className="text-[10px] font-medium uppercase text-muted-foreground/80 tracking-wide">
              {localized}
            </span>
            <span className="text-base leading-none" aria-hidden="true">
              {day.icon_emoji}
            </span>
            <span className="text-[10px] tabular-nums leading-tight">
              <span className="font-semibold text-foreground">{Math.round(day.temp_max_c)}°</span>
              <span className="text-muted-foreground/70"> / {Math.round(day.temp_min_c)}°</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

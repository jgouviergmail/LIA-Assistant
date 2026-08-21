'use client';

import {
  CloudDrizzle,
  CloudLightning,
  CloudRain,
  CloudSun,
  Droplets,
  Flower2,
  Snowflake,
  Wind,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import type { ComponentType } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { BriefingCard } from '../BriefingCard';
import type {
  AirQuality,
  CardSection,
  DailyForecastItem,
  ForecastAlert,
  ForecastAlertKind,
  PollenItem,
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

/**
 * Build the wind line, or `null` when the provider sent no speed.
 *
 * `wind_direction_cardinal` is a CODE (N/NE/E/SE/S/SW/W/NW), not a label:
 * German writes "O" for Ost where English writes "E", and the Romance
 * languages write "O" for Ouest/Oeste/Ovest where English writes "W".
 * Printing it raw showed a French reader "15 km/h W" for a westerly wind.
 * A code the locale has no entry for resolves to the empty default and the
 * bearing is simply dropped — a raw code is worse than no bearing at all.
 */
function windLabelFor(
  data: Pick<WeatherData, 'wind_speed_kmh' | 'wind_direction_cardinal'>,
  t: (key: string, options?: { defaultValue?: string }) => string
): string | null {
  if (data.wind_speed_kmh === null) return null;
  const cardinal = data.wind_direction_cardinal
    ? t(`dashboard.briefing.cards.weather.wind_cardinal.${data.wind_direction_cardinal}`, {
        defaultValue: '',
      })
    : '';
  const speed = `${Math.round(data.wind_speed_kmh)} km/h`;
  return cardinal ? `${speed} ${cardinal}` : speed;
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
  const windLabel = windLabelFor(data, t);

  // Enrichment fields (2026-08) read defensively: the briefing caches
  // sections for up to an hour and a rolling deploy can serve a payload
  // predating these fields.
  const airQuality = data.air_quality ?? null;
  const pollen = data.pollen ?? [];

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
          <span className="text-muted-foreground"> · {data.location_city}</span>
        )}
      </p>

      <MetricsRow windLabel={windLabel} popPct={popPct} alert={data.forecast_alert} />

      <EnvironmentRow airQuality={airQuality} pollen={pollen} />

      {/* 5-day forecast strip */}
      {data.daily_forecast.length > 0 && (
        <div className="w-full pt-2 border-t border-border/30">
          <DailyForecastStrip days={data.daily_forecast} />
        </div>
      )}
    </div>
  );
}

/** Wind + rain probability + forecast alert, in one compact row. */
function MetricsRow({
  windLabel,
  popPct,
  alert,
}: {
  windLabel: string | null;
  popPct: number | null;
  alert: ForecastAlert | null;
}) {
  if (windLabel === null && popPct === null && alert === null) return null;

  return (
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
      {alert && <ForecastAlertBadge alert={alert} />}
    </div>
  );
}

/**
 * Air quality + pollen (2026-08) — same compact metrics language as the wind
 * row, so the card gains a signal without gaining a section. Rendering lives
 * in its own component: the parent already carries the hero, the metrics row
 * and the forecast strip.
 */
function EnvironmentRow({
  airQuality,
  pollen,
}: {
  airQuality: AirQuality | null;
  pollen: PollenItem[];
}) {
  const { t } = useTranslation();
  if (airQuality === null && pollen.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {airQuality !== null && (
        <span
          className="inline-flex items-center gap-1"
          data-testid="weather-air-quality"
          title={t('dashboard.briefing.cards.weather.air_quality')}
        >
          <Wind className="h-3 w-3" aria-hidden="true" />
          <span>{airQualityLabel(airQuality)}</span>
        </span>
      )}
      {pollen.length > 0 && (
        <span
          className="inline-flex items-center gap-1"
          data-testid="weather-pollen"
          title={t('dashboard.briefing.cards.weather.pollen')}
        >
          <Flower2 className="h-3 w-3" aria-hidden="true" />
          <span>{pollenLabel(pollen)}</span>
        </span>
      )}
    </div>
  );
}

/**
 * Air-quality line: the provider's own localized category, prefixed by the
 * index value when the chosen index carries one, and suffixed by the index
 * name. Never re-derives a label from the number (Google's universal index is
 * inverted vs EPA), and never invents a number a national index omitted.
 */
function airQualityLabel(air: AirQuality): string {
  const head = air.value !== null ? `${air.value} · ${air.category}` : air.category;
  return air.index_label ? `${head} (${air.index_label})` : head;
}

/** Pollen line: "Graminées Élevé, Ambroisie Faible" — categories verbatim. */
function pollenLabel(pollen: PollenItem[]): string {
  return pollen.map(item => [item.name, item.category].filter(Boolean).join(' ')).join(', ');
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
            <span className="text-[10px] font-medium uppercase text-muted-foreground tracking-wide">
              {localized}
            </span>
            <span className="text-base leading-none" aria-hidden="true">
              {day.icon_emoji}
            </span>
            <span className="text-[10px] tabular-nums leading-tight">
              <span className="font-semibold text-foreground">{Math.round(day.temp_max_c)}°</span>
              <span className="text-muted-foreground"> / {Math.round(day.temp_min_c)}°</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

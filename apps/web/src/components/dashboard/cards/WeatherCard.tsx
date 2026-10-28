'use client';
import { useDashboardRoute } from '../DashboardNavigation';

import {
  CloudDrizzle,
  CloudLightning,
  CloudRain,
  CloudSun,
  Droplets,
  Flower2,
  Leaf,
  Snowflake,
  Wind,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import type { ComponentType } from 'react';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { WeatherConditionIcon, WeatherIllustration } from './WeatherIllustration';
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
  const navigate = useDashboardRoute(router.push);
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
      onErrorCta={() => navigate(`/${lng}/dashboard/settings?section=connectors`)}
      renderContent={data => <WeatherContent data={data} />}
      staggerIndex={staggerIndex}
    />
  );
}

export function WeatherContent({ data }: { data: WeatherData }) {
  const { t } = useTranslation();
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
    <div className="@container w-full space-y-3 text-left">
      {data.location_city && (
        <p className="break-words text-sm text-muted-foreground">{data.location_city}</p>
      )}
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] items-center gap-2">
        <div className="min-w-0 space-y-3">
          <p className="my-1 text-[clamp(2rem,16cqw,3.75rem)] font-medium leading-none tracking-[-0.04em] tabular-nums text-foreground">
            {tempLabel}
          </p>
          <p className="break-words text-xs leading-relaxed text-foreground [overflow-wrap:anywhere]">
            <span className="capitalize">{data.description}</span>
            {minMax && (
              <span className="ml-2 whitespace-nowrap text-muted-foreground tabular-nums">
                {minMax}
              </span>
            )}
          </p>
          <MetricsRow windLabel={windLabel} popPct={popPct} alert={data.forecast_alert} />
          <EnvironmentRow airQuality={airQuality} pollen={pollen} />
        </div>
        <WeatherIllustration conditionCode={data.condition_code} fallbackEmoji={data.icon_emoji} />
      </div>
      {/* 5-day forecast strip */}
      {data.daily_forecast.length > 0 && (
        <div className="w-full pt-2 border-t border-border">
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
    <div className="flex flex-wrap items-center justify-start gap-x-4 gap-y-2 text-xs text-muted-foreground">
      {windLabel !== null && (
        <span className="inline-flex min-w-0 items-center gap-1.5">
          <Wind className="size-3.5 shrink-0 text-primary" aria-hidden="true" />
          <span className="tabular-nums">{windLabel}</span>
        </span>
      )}
      {popPct !== null && (
        <span className="inline-flex min-w-0 items-center gap-1.5">
          <Droplets className="size-3.5 shrink-0 text-primary" aria-hidden="true" />
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
    <div className="flex flex-wrap items-center justify-start gap-x-4 gap-y-2 text-xs text-muted-foreground">
      {airQuality !== null && (
        <span
          className="inline-flex min-w-0 items-center gap-1.5"
          data-testid="weather-air-quality"
          title={t('dashboard.briefing.cards.weather.air_quality')}
        >
          <Leaf className="size-3.5 shrink-0 text-primary" aria-hidden="true" />
          <span className="min-w-0 break-words [overflow-wrap:anywhere]">
            {airQualityLabel(airQuality)}
          </span>
        </span>
      )}
      {pollen.length > 0 && (
        <span
          className="inline-flex min-w-0 items-center gap-1.5"
          data-testid="weather-pollen"
          title={t('dashboard.briefing.cards.weather.pollen')}
        >
          <Flower2 className="size-3.5 shrink-0 text-primary" aria-hidden="true" />
          <span className="min-w-0 break-words [overflow-wrap:anywhere]">
            {pollenLabel(pollen)}
          </span>
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
    <span className="inline-flex items-center gap-1 font-medium text-muted-foreground">
      <Icon className="size-3.5 shrink-0 text-primary" aria-hidden={true} />
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
      style={{ gridTemplateColumns: `repeat(${Math.min(days.length, 5)}, minmax(0, 1fr))` }}
      role="list"
    >
      {days.map(day => {
        // date_iso is 'YYYY-MM-DD' in user TZ; appending T00:00 keeps the
        // intended day stable when interpreted as local time.
        const localized = weekdayFormatter.format(new Date(`${day.date_iso}T00:00`));
        return (
          <li
            key={day.date_iso}
            className="flex min-w-0 flex-col items-center gap-1.5 text-center"
            title={`${day.date_iso} · ${day.condition_code}`}
          >
            <time dateTime={day.date_iso} className="text-xs capitalize text-muted-foreground">
              {localized}
            </time>
            <WeatherConditionIcon
              conditionCode={day.condition_code}
              fallbackEmoji={day.icon_emoji}
            />
            <span className="text-xs font-semibold text-foreground tabular-nums">
              {Math.round(day.temp_max_c)}°
            </span>
            <span className="text-xs text-muted-foreground tabular-nums">
              {Math.round(day.temp_min_c)}°
            </span>
          </li>
        );
      })}
    </ul>
  );
}

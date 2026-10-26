'use client';
import { formatDate } from '@/lib/format';
import { Button } from '@/components/ui/button';
import { WeatherContent } from '@/components/dashboard/cards/WeatherCard';
import { useAuth } from '@/hooks/useAuth';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { CardSection, WeatherData } from '@/types/briefing';

interface Props {
  lng: Language;
  ownerId: string;
  onAsk(): void;
}
export function WorldWeatherPanel(props: Props) {
  const { user } = useAuth();
  if (user?.id !== props.ownerId) return null;
  return <OwnedWeather key={props.ownerId} {...props} timezone={user.timezone} />;
}
function OwnedWeather({ lng, ownerId, onAsk, timezone }: Props & { timezone?: string }) {
  const { t } = useTranslation(lng);
  const query = useApiQuery<CardSection<WeatherData> | null>('/briefing/cached-weather', {
    componentName: 'WorldCachedForecast',
    deps: [ownerId],
  });
  const section = query.data;
  const failed = query.error || section?.status === 'error';
  return (
    <div className="space-y-4">
      {query.loading ? (
        <p role="status">{t('common.loading')}</p>
      ) : section?.data ? (
        <ForecastObservation lng={lng} timezone={timezone} section={section} data={section.data} />
      ) : (
        <p role={failed ? 'alert' : undefined}>
          {section?.error_message ||
            t(failed ? 'world.session.unavailable' : 'dashboard.briefing.cards.weather.empty')}
        </p>
      )}
      <Button onClick={onAsk}>{t('world.lia_menu.conversation')}</Button>
    </div>
  );
}

/** The date belongs to the shown observation, never to its failed refresh. */
function ForecastObservation({
  lng,
  timezone,
  section,
  data,
}: {
  lng: Language;
  timezone?: string;
  section: CardSection<WeatherData>;
  data: WeatherData;
}) {
  const { t } = useTranslation(lng);
  const isError = section.status === 'error';
  const generatedAt = isError ? section.stale_generated_at : section.generated_at;
  return (
    <>
      {isError && (
        <p role="status">{section.error_message || t('dashboard.briefing.errors.generic')}</p>
      )}
      <WeatherContent data={data} />
      {generatedAt && (
        <time className="block text-xs text-muted-foreground" dateTime={generatedAt}>
          {formatDate(generatedAt, lng, {
            dateStyle: 'medium',
            timeStyle: 'short',
            timeZone: timezone,
          })}
        </time>
      )}
    </>
  );
}

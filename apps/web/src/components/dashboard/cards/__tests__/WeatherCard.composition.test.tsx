/** The approved home weather composition, driven only by received weather. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { CardSection, DailyForecastItem, WeatherData } from '@/types/briefing';

const { language } = vi.hoisted(() => ({ language: { current: 'fr' } }));
function translate(
  key: string,
  options?: { value?: number; time?: string; context?: string; defaultValue?: string }
) {
  if (key === 'dashboard.briefing.cards.weather.temp') return `${options?.value}°C`;
  if (key === 'dashboard.briefing.cards.weather.forecast_alert') return `Pluie à ${options?.time}`;
  if (key.includes('.wind_cardinal.')) return options?.defaultValue ?? '';
  return key;
}
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: translate, i18n: { language: language.current } }),
}));

import { WeatherCard } from '../WeatherCard';

function forecast(overrides: Partial<DailyForecastItem> = {}): DailyForecastItem {
  return {
    date_iso: '2026-10-15',
    temp_min_c: 12,
    temp_max_c: 23,
    condition_code: 'Clear',
    icon_emoji: '☀️',
    ...overrides,
  };
}
function weather(overrides: Partial<WeatherData> = {}): CardSection<WeatherData> {
  return {
    status: 'ok',
    generated_at: '2026-10-15T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
    data: {
      temperature_c: 22.6,
      temperature_min_c: 14,
      temperature_max_c: 24,
      condition_code: 'Clear',
      description: 'Éclaircies',
      icon_emoji: '☀️',
      location_city: 'Bordeaux',
      wind_speed_kmh: 12,
      wind_direction_cardinal: null,
      precipitation_probability: 0.1,
      forecast_alert: { kind: 'rain', time: '18:00' },
      daily_forecast: [forecast()],
      air_quality: {
        value: 66,
        category: 'Bonne qualité fournisseur',
        index_label: 'Universal AQI',
      },
      pollen: [
        { name: 'Graminées', category: 'Faible fournisseur', index: 1 },
        { name: 'Ambroisie', category: 'Élevé fournisseur', index: 4 },
      ],
      ...overrides,
    },
  };
}
function show(overrides: Partial<WeatherData> = {}) {
  return renderWithProviders(
    <WeatherCard section={weather(overrides)} isRefreshing={false} onRefresh={vi.fn()} />
  );
}
function before(first: HTMLElement, second: HTMLElement) {
  return Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);
}
beforeEach(() => {
  language.current = 'fr';
});

describe('WeatherCard approved composition', () => {
  it('places the received city above temperature, then description, measurements and environment before forecast', () => {
    show();
    const city = screen.getByText('Bordeaux');
    const temperature = screen.getByText('23°C');
    const description = screen.getByText('Éclaircies');
    const wind = screen.getByText('12 km/h');
    const air = screen.getByText('66 · Bonne qualité fournisseur (Universal AQI)');
    const day = screen.getByText('jeu.');
    expect(before(city, temperature)).toBe(true);
    expect(before(temperature, description)).toBe(true);
    expect(before(description, wind)).toBe(true);
    expect(before(wind, air)).toBe(true);
    expect(before(air, day)).toBe(true);
    expect(screen.getByText('14° / 24°')).toBeVisible();
    expect(screen.getByText('10%')).toBeVisible();
    expect(screen.getByText('Pluie à 18:00')).toBeVisible();
    expect(
      screen.getByText('Graminées Faible fournisseur, Ambroisie Élevé fournisseur')
    ).toBeVisible();
  });

  it.each([
    ['fr', 'jeu.'],
    ['en', 'Thu'],
    ['de', 'Do'],
    ['es', 'jue'],
    ['it', 'gio'],
    ['zh', '周四'],
  ])('keeps forecast date and separate high/low values in %s', (locale, weekday) => {
    language.current = locale;
    show();
    const item = screen.getByRole('listitem');
    const date = within(item).getByText(weekday);
    expect(date.tagName).toBe('TIME');
    expect(date).toHaveAttribute('datetime', '2026-10-15');
    expect(within(item).getByText('23°')).toBeVisible();
    expect(within(item).getByText('12°')).toBeVisible();
  });

  it.each([
    'Clear',
    'Clouds',
    'Rain',
    'Drizzle',
    'Thunderstorm',
    'Snow',
    'Fog',
    'Squall',
    'Unrecognized',
    '__proto__',
    'constructor',
  ])('draws the actual %s condition without a false sunny sky', condition => {
    show({ condition_code: condition, description: `Provider ${condition}`, icon_emoji: '❔' });
    expect(screen.getByText(`Provider ${condition}`)).toBeVisible();
    const landscape = screen.getByTestId('weather-landscape');
    // Cloud and hill silhouettes are paths; only a confirmed clear sky has
    // solar circles. This checks the actual drawn SVG, not a style name.
    expect(landscape.querySelectorAll('circle').length > 0).toBe(condition === 'Clear');
    if (['Unrecognized', '__proto__', 'constructor'].includes(condition))
      expect(within(landscape).getByText('❔')).toBeInTheDocument();
  });

  it('preserves every received forecast and long provider environmental label', () => {
    const days = Array.from({ length: 7 }, (_, day) =>
      forecast({
        date_iso: `2026-10-${15 + day}`,
        temp_max_c: 20 + day,
        temp_min_c: 10 + day,
      })
    );
    show({
      daily_forecast: days,
      air_quality: {
        value: null,
        category: 'Catégorie nationale intégrale reçue du fournisseur',
        index_label: 'IQA (FR)',
      },
    });
    expect(screen.getAllByRole('listitem')).toHaveLength(7);
    expect(
      screen.getByText('Catégorie nationale intégrale reçue du fournisseur (IQA (FR))')
    ).toBeVisible();
    expect(within(screen.getAllByRole('listitem')[6]).getByText('26°')).toBeVisible();
    expect(within(screen.getAllByRole('listitem')[6]).getByText('16°')).toBeVisible();
  });

  it('does not invent optional city, forecasts, wind, rain or environmental data', () => {
    show({
      location_city: null,
      temperature_min_c: null,
      temperature_max_c: null,
      wind_speed_kmh: null,
      precipitation_probability: null,
      forecast_alert: null,
      air_quality: null,
      pollen: [],
      daily_forecast: [],
    });
    expect(screen.getByText('23°C')).toBeVisible();
    expect(screen.getByText('Éclaircies')).toBeVisible();
    expect(screen.queryByText('Bordeaux')).not.toBeInTheDocument();
    expect(screen.queryByText(/km\/h|%|Universal AQI|Graminées/)).not.toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });
});

/**
 * The weather card's wind line — the one string the backend deliberately does
 * NOT translate.
 *
 * `wind_direction_cardinal` is a CODE (N/NE/E/SE/S/SW/W/NW) because the
 * abbreviations are language-specific: German writes "O" for Ost where English
 * writes "E", and French/Spanish/Italian write "O" for Ouest/Oeste/Ovest where
 * English writes "W". The card used to interpolate the code straight into the
 * line, so a French reader saw "15 km/h W" for a westerly wind.
 *
 * The global i18n stub echoes keys, which would make every assertion here
 * vacuous — so this file drives a controlled dictionary instead.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { render, screen } from '@/__tests__/test-utils';
import type { CardSection, WeatherData } from '@/types/briefing';

/** Compass abbreviations, mirroring locales/{fr,en,de}/translation.json. */
const DICTIONARIES: Record<string, Record<string, string>> = {
  fr: { N: 'N', NE: 'NE', E: 'E', SE: 'SE', S: 'S', SW: 'SO', W: 'O', NW: 'NO' },
  en: { N: 'N', NE: 'NE', E: 'E', SE: 'SE', S: 'S', SW: 'SW', W: 'W', NW: 'NW' },
  de: { N: 'N', NE: 'NO', E: 'O', SE: 'SO', S: 'S', SW: 'SW', W: 'W', NW: 'NW' },
};

const { state } = vi.hoisted(() => ({ state: { language: 'fr' } }));

const CARDINAL_PREFIX = 'dashboard.briefing.cards.weather.wind_cardinal.';

/** `t` resolving only the compass namespace; every other key echoes. */
function translate(key: string, options?: { value?: number; defaultValue?: string }): string {
  if (key.startsWith(CARDINAL_PREFIX)) {
    const code = key.slice(CARDINAL_PREFIX.length);
    return DICTIONARIES[state.language]?.[code] ?? options?.defaultValue ?? '';
  }
  if (key === 'dashboard.briefing.cards.weather.temp') {
    return `${options?.value}°C`;
  }
  return key;
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: translate,
    i18n: { language: state.language, changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}));
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: translate,
    i18n: { language: state.language, changeLanguage: vi.fn() },
  }),
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { WeatherCard } from '../WeatherCard';

function weatherSection(overrides: Partial<WeatherData> = {}): CardSection<WeatherData> {
  return {
    status: 'ok',
    data: {
      temperature_c: 18.4,
      temperature_min_c: 12,
      temperature_max_c: 21,
      condition_code: 'Clear',
      description: 'Ciel dégagé',
      icon_emoji: '☀️',
      location_city: 'Paris',
      wind_speed_kmh: 15.2,
      wind_direction_cardinal: 'W',
      precipitation_probability: null,
      forecast_alert: null,
      daily_forecast: [],
      air_quality: null,
      pollen: [],
      ...overrides,
    },
    generated_at: '2026-07-25T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

function renderCard(overrides: Partial<WeatherData> = {}) {
  return render(
    <WeatherCard section={weatherSection(overrides)} isRefreshing={false} onRefresh={vi.fn()} />
  );
}

beforeEach(() => {
  state.language = 'fr';
  vi.clearAllMocks();
});

describe('WeatherCard — wind direction', () => {
  it('renders the French abbreviation for a westerly wind', () => {
    renderCard({ wind_direction_cardinal: 'W' });

    expect(screen.getByText('15 km/h O')).toBeInTheDocument();
    expect(screen.queryByText('15 km/h W')).not.toBeInTheDocument();
  });

  it.each([
    ['fr', 'SW', '15 km/h SO'],
    ['en', 'SW', '15 km/h SW'],
    ['de', 'E', '15 km/h O'],
    ['en', 'E', '15 km/h E'],
    ['de', 'NE', '15 km/h NO'],
  ])('renders %s/%s as "%s"', (language, code, expected) => {
    state.language = language;
    renderCard({ wind_direction_cardinal: code });

    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it('never leaks the translation key into the card', () => {
    renderCard({ wind_direction_cardinal: 'NW' });

    expect(screen.queryByText(new RegExp(CARDINAL_PREFIX))).not.toBeInTheDocument();
  });

  it('drops the direction rather than printing a raw code the locale ignores', () => {
    // A code absent from the dictionary resolves to the empty default.
    renderCard({ wind_direction_cardinal: 'NNE' });

    expect(screen.getByText('15 km/h')).toBeInTheDocument();
  });

  it('shows the speed alone when the provider sent no bearing', () => {
    renderCard({ wind_direction_cardinal: null });

    expect(screen.getByText('15 km/h')).toBeInTheDocument();
  });

  it('shows no wind line at all when the speed is missing', () => {
    renderCard({ wind_speed_kmh: null, wind_direction_cardinal: 'W' });

    expect(screen.queryByText(/km\/h/)).not.toBeInTheDocument();
  });

  it('rounds the speed to the nearest km/h', () => {
    renderCard({ wind_speed_kmh: 15.6, wind_direction_cardinal: 'N' });

    expect(screen.getByText('16 km/h N')).toBeInTheDocument();
  });
});

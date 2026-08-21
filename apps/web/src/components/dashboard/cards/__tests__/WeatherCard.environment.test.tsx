/**
 * Air quality and pollen on the home-page weather card (2026-08).
 *
 * The enrichment reached the chat card first; the briefing card — the surface
 * the user sees FIRST — stayed unchanged (reported in prod, 2026-08-21).
 *
 * Two rules the rendering must respect, both learned from the real payload:
 * - a national index ships a localized CATEGORY with NO numeric value, so the
 *   row must render on the category, never gate on the number;
 * - the provider's own category wins: Google's universal index is inverted vs
 *   EPA (100 = excellent), so the client never re-derives a label.
 */

import { describe, it, expect, vi } from 'vitest';

import { render, screen } from '@/__tests__/test-utils';
import type { CardSection, WeatherData } from '@/types/briefing';

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

describe('WeatherCard — air quality', () => {
  it('renders a category that has no numeric value', () => {
    renderCard({
      air_quality: { value: null, category: 'Moyen', index_label: 'IQA (FR)' },
    });

    expect(screen.getByText(/Moyen/)).toBeInTheDocument();
    expect(screen.getByText(/IQA \(FR\)/)).toBeInTheDocument();
  });

  it('renders the value alongside its own category', () => {
    renderCard({
      air_quality: { value: 66, category: 'Bonne qualité', index_label: 'Universal AQI' },
    });

    expect(screen.getByText(/66/)).toBeInTheDocument();
    expect(screen.getByText(/Bonne qualité/)).toBeInTheDocument();
  });

  it('renders nothing when the enrichment is absent', () => {
    renderCard();

    expect(screen.queryByText(/Moyen/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('weather-air-quality')).not.toBeInTheDocument();
  });
});

describe('WeatherCard — payloads predating the enrichment', () => {
  it('renders a cached payload that has neither field', () => {
    // The briefing caches its sections (TTL up to an hour) and a rolling
    // deploy can serve an older API: the card must survive a payload where
    // `air_quality` / `pollen` are simply absent, not blank out the page.
    const section = weatherSection();
    const legacy = { ...section.data } as Record<string, unknown>;
    delete legacy.air_quality;
    delete legacy.pollen;

    render(
      <WeatherCard
        section={{ ...section, data: legacy as unknown as WeatherData }}
        isRefreshing={false}
        onRefresh={vi.fn()}
      />
    );

    expect(screen.getByText(/Ciel dégagé/)).toBeInTheDocument();
    expect(screen.queryByTestId('weather-air-quality')).not.toBeInTheDocument();
    expect(screen.queryByTestId('weather-pollen')).not.toBeInTheDocument();
  });
});

describe('WeatherCard — pollen', () => {
  it('lists in-season pollen types with their severity', () => {
    renderCard({
      pollen: [
        { name: 'Graminées', category: 'Élevé', index: 4 },
        { name: 'Ambroisie', category: 'Faible', index: 1 },
      ],
    });

    expect(screen.getByText(/Graminées/)).toBeInTheDocument();
    expect(screen.getByText(/Élevé/)).toBeInTheDocument();
    expect(screen.getByText(/Ambroisie/)).toBeInTheDocument();
  });

  it('renders nothing when there is no in-season pollen', () => {
    renderCard({ pollen: [] });

    expect(screen.queryByTestId('weather-pollen')).not.toBeInTheDocument();
  });
});

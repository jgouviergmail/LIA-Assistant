import type { ComponentProps } from 'react';
import { screen } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider, initReactI18next } from 'react-i18next';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/__tests__/test-utils';
import { AuthContext, type User } from '@/lib/auth';
import { parsePlaceRoute } from '@/lib/place-route-data';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { PlaceMapDetails } from '../place-map-details';

vi.mock('react-i18next', async original => original<typeof import('react-i18next')>());

type Props = ComponentProps<typeof PlaceMapDetails>;
const place: Props['place'] = {
  ref: 'east',
  label: 'Café des amis',
  url: 'https://www.google.com/maps/place/?q=east',
  position: { lat: 0, lng: 179.9 },
  details: {
    address: '12 rue du Port',
    rating: 0,
    reviews_count: 0,
    phone: '+33 (0)1 23 45 67 89',
    website: 'https://cafe.example.test/',
    opening_hours: ['Lundi : 09:00–18:00'],
  },
};
const idle: Props['route'] = { status: 'idle', ref: null, result: null, error: null };
const user: User = {
  id: 'a',
  email: 'a@example.test',
  is_active: true,
  is_verified: true,
  is_superuser: false,
  memory_enabled: false,
  execution_mode: 'pipeline',
  voice_enabled: false,
  voice_mode_enabled: false,
  voice_stt_mode: 'local',
  tokens_display_enabled: false,
  debug_panel_enabled: false,
  response_display_mode: 'cards',
  onboarding_completed: true,
  timezone: 'Pacific/Honolulu',
};
const auth = {
  user,
  isLoading: false,
  login: vi.fn(),
  verifyMfa: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  initiateGoogleOAuth: vi.fn(),
  completeNativeSignIn: vi.fn(),
  refreshUser: vi.fn(),
};

async function view(language: string, route = idle, selected = place) {
  const i18n = createInstance();
  await i18n.use(initReactI18next).init({
    lng: language,
    fallbackLng: false,
    resources: { en: { translation: en }, fr: { translation: fr } },
    interpolation: { escapeValue: false },
  });
  const retry = vi.fn();
  const tree = (next: Props['route']) => (
    <I18nextProvider i18n={i18n}>
      <AuthContext.Provider value={auth}>
        <PlaceMapDetails place={selected} route={next} onRetry={retry} />
      </AuthContext.Provider>
    </I18nextProvider>
  );
  return { ...renderWithProviders(tree(route)), tree, retry };
}

describe('selected place details', () => {
  it.each([
    { language: 'en', hours: 'Opening hours', website: 'Website', refresh: 'Refresh route' },
    {
      language: 'fr',
      hours: 'Horaires',
      website: 'Site internet',
      refresh: 'Actualiser le trajet',
    },
  ])('names facts and controls in $language without losing zero values', async sample => {
    const result = await view(sample.language);
    expect(screen.getByRole('region', { name: place.label })).toBeVisible();
    expect(screen.getByRole('heading', { name: place.label })).toBeVisible();
    expect(screen.getByText('12 rue du Port')).toBeVisible();
    expect(screen.getByText(/0.*5.*0/)).toBeVisible();
    expect(screen.getByRole('link', { name: sample.website })).toHaveAttribute(
      'href',
      place.details?.website
    );
    expect(screen.getByRole('link', { name: place.details?.phone ?? '' })).toHaveAttribute(
      'href',
      'tel:+330123456789'
    );
    await result.user.click(screen.getByText(sample.hours));
    expect(screen.getByText('Lundi : 09:00–18:00')).toBeVisible();
    await result.user.click(screen.getByRole('button', { name: sample.refresh }));
    expect(result.retry).toHaveBeenCalledOnce();
  });

  it('keeps details and retry focus through loading, origin error and retry', async () => {
    const result = await view('fr', { ...idle, status: 'error', ref: place.ref, error: 'origin' });
    const refresh = screen.getByRole('button', { name: 'Actualiser le trajet' });
    await result.user.click(refresh);
    result.rerender(result.tree({ ...idle, status: 'loading', ref: place.ref }));
    expect(refresh).toHaveFocus();
    expect(refresh).toHaveAttribute('aria-disabled', 'true');
    await result.user.click(refresh);
    expect(result.retry).toHaveBeenCalledOnce();
    result.rerender(result.tree({ ...idle, status: 'error', ref: place.ref, error: 'origin' }));
    expect(refresh).toHaveFocus();
    expect(screen.getByRole('alert')).toHaveTextContent('renseigne ton domicile');
    expect(screen.getByText('12 rue du Port')).toBeVisible();
    await result.user.click(refresh);
    expect(result.retry).toHaveBeenCalledTimes(2);
  });

  it('labels last-known age in the account timezone and displays route facts', async () => {
    const asOf = '2026-01-02T03:00:00+00:00';
    const route = parsePlaceRoute({
      origin_source: 'last_known',
      origin_as_of: asOf,
      travel_mode: 'WALK',
      polyline: '??_ibE_ibE',
      distance_meters: 1200,
      duration_seconds: 180,
    });
    expect(route).not.toBeNull();
    await view('en', { status: 'ready', ref: place.ref, result: route, error: null });
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('last known');
    expect(status).toHaveTextContent(
      new Intl.DateTimeFormat('en', {
        dateStyle: 'short',
        timeStyle: 'short',
        timeZone: user.timezone,
      }).format(new Date(asOf))
    );
    expect(status).toHaveTextContent('Distance1.2 km');
    expect(status).toHaveTextContent('Duration3 min');
  });

  it('retains the Google source link for an old archive with no facts', async () => {
    await view('en', idle, { ...place, details: undefined });
    expect(screen.getAllByRole('link')).toHaveLength(1);
    expect(screen.getByRole('link')).toHaveAttribute('href', place.url);
    expect(screen.queryByText('12 rue du Port')).toBeNull();
  });
});

import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider, initReactI18next } from 'react-i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/__tests__/test-utils';
import { AppConfigSeedContext, type AppConfig } from '@/hooks/useAppConfig';
import { apiClient } from '@/lib/api-client';
import { loadRouteMaps, mountRouteMap } from '@/lib/google-route-map';
import { reportRouteMapLoad } from '@/lib/route-map-metering';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', async original => original<typeof import('react-i18next')>());
vi.mock('@/lib/google-route-map', () => ({ loadRouteMaps: vi.fn(), mountRouteMap: vi.fn() }));
vi.mock('@/lib/route-map-metering', async original => ({
  ...(await original<typeof import('@/lib/route-map-metering')>()),
  reportRouteMapLoad: vi.fn(),
}));
const wire = JSON.stringify({
  version: 1,
  primary_id: 'route-1',
  omitted_count: 0,
  routes: [
    { id: 'route-0', polyline: '??_ibE_ibE', distance_meters: 0, duration_seconds: 0 },
    { id: 'route-1', polyline: '??_seK_seK', distance_meters: 1200, duration_seconds: 180 },
  ],
});
const html = `<div class="lia-route-map" data-route-map="${wire.replaceAll('"', '&quot;')}"><a href="https://www.google.com/maps">SOURCE_MAP</a></div>`;
const seed: AppConfig = {
  sse: { heartbeat_interval_seconds: 30 },
  rate_limits: { enabled: true, per_minute: 30, burst: 10 },
  i18n: { supported_languages: ['en', 'fr'], default_language: 'en' },
  features: {
    interactive_route_maps_enabled: true,
    tool_approval_enabled: true,
    attachments_enabled: true,
    rag_spaces_enabled: false,
    rag_spaces_embedding_model: 'none',
    journals_enabled: false,
  },
  route_maps: { enabled: true, estimated_cost_eur: '0.006' },
  api_version: '1',
};
const controller = { select: vi.fn(), fit: vi.fn(), destroy: vi.fn() };
async function view(language = 'en', config: AppConfig | null = seed, content = html) {
  const i18n = createInstance();
  await i18n.use(initReactI18next).init({
    lng: language,
    fallbackLng: false,
    resources: { en: { translation: en }, fr: { translation: fr } },
    interpolation: { escapeValue: false },
  });
  return {
    i18n,
    ...renderWithProviders(
      <I18nextProvider i18n={i18n}>
        <AppConfigSeedContext.Provider value={config}>
          <MarkdownContent content={content} />
        </AppConfigSeedContext.Provider>
      </I18nextProvider>
    ),
  };
}
beforeEach(() => {
  vi.mocked(loadRouteMaps).mockResolvedValue({
    MapTypeControlStyle: { DROPDOWN_MENU: 1 },
    Map: vi.fn(),
    Polyline: vi.fn(),
    LatLngBounds: vi.fn(),
    event: { clearInstanceListeners: vi.fn() },
  });
  vi.mocked(mountRouteMap).mockImplementation(
    (_maps, _element, _data, _select, _failure, onConstruct) => {
      onConstruct?.();
      return controller;
    }
  );
  vi.mocked(reportRouteMapLoad).mockResolvedValue();
  vi.spyOn(apiClient, 'post').mockResolvedValue({
    api_key: 'public-browser-key',
    load_token: 'account-bound-grant',
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
});
describe('exact route map from sanitized archived HTML', () => {
  it('refuses a malformed admission before loading any external SDK', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ api_key: { unsafe: 'shape' }, load_token: null });
    await view();
    fireEvent.click(screen.getByRole('button', { name: 'Explore map' }));
    await screen.findByRole('alert');
    expect(loadRouteMaps).not.toHaveBeenCalled();
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
  });
  it('receives the authenticated layout config when it arrives after the card', async () => {
    const result = await view('en', null);
    expect(screen.queryByRole('button', { name: 'Explore map' })).toBeNull();
    result.rerender(
      <I18nextProvider i18n={result.i18n}>
        <AppConfigSeedContext.Provider value={seed}>
          <MarkdownContent content={html} />
        </AppConfigSeedContext.Provider>
      </I18nextProvider>
    );
    expect(screen.getByRole('button', { name: 'Explore map' })).toBeVisible();
  });
  it.each([
    {
      language: 'en',
      activate: 'Explore map',
      primary: 'Primary',
      alternative: 'Alternative 1',
      region: 'Interactive route map',
    },
    {
      language: 'fr',
      activate: 'Explorer la carte',
      primary: 'Principal',
      alternative: 'Alternative 1',
      region: 'Carte interactive des itinéraires',
    },
  ])('names controls in $language and changes facts without another paid load', async sample => {
    const result = await view(sample.language);
    expect(loadRouteMaps).not.toHaveBeenCalled();
    const activate = screen.getByRole('button', { name: sample.activate });
    activate.focus();
    fireEvent.click(activate);
    await screen.findByRole('region', { name: sample.region });
    expect(activate).toHaveFocus();
    expect(screen.getByRole('button', { name: new RegExp(sample.primary) })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    const alternative = screen.getByRole('button', { name: new RegExp(sample.alternative) });
    fireEvent.click(alternative);
    expect(alternative).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('status')).toHaveTextContent('0 km · 0 min');
    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(reportRouteMapLoad).toHaveBeenCalledWith('account-bound-grant');
    expect(controller.select).toHaveBeenLastCalledWith('route-0');
    result.unmount();
    expect(controller.destroy).toHaveBeenCalledOnce();
  });
  it('retains the source on configuration/geometry refusal without SDK requests', async () => {
    await view(
      'en',
      { ...seed, route_maps: { enabled: false } },
      html.replace('route-1', 'unknown')
    );
    expect(screen.getByRole('link', { name: 'SOURCE_MAP' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Explore map' })).toBeNull();
    expect(apiClient.post).not.toHaveBeenCalled();
  });
  it('keeps the trigger focus and fallback on SDK failure, never reporting a load', async () => {
    vi.mocked(loadRouteMaps).mockRejectedValue(new Error('SDK unavailable'));
    await view();
    const button = screen.getByRole('button', { name: 'Explore map' });
    button.focus();
    fireEvent.click(button);
    await screen.findByRole('alert');
    expect(button).toHaveFocus();
    expect(screen.getByRole('link', { name: 'SOURCE_MAP' })).toBeVisible();
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
  });
  it('refuses repeated pending activations and never constructs a map after unmount', async () => {
    let resolve: ((value: { api_key: string; load_token: string }) => void) | undefined;
    vi.mocked(apiClient.post).mockReturnValue(
      new Promise(done => {
        resolve = done;
      })
    );
    const result = await view();
    const button = screen.getByRole('button', { name: 'Explore map' });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(apiClient.post).toHaveBeenCalledOnce();
    result.unmount();
    await act(async () => resolve?.({ api_key: 'public-key', load_token: 'grant' }));
    expect(mountRouteMap).not.toHaveBeenCalled();
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
  });
  it('retries a lost report with the same grant and never constructs another map', async () => {
    vi.mocked(reportRouteMapLoad)
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce();
    await view();
    fireEvent.click(screen.getByRole('button', { name: 'Explore map' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(vi.mocked(reportRouteMapLoad).mock.calls).toEqual([
      ['account-bound-grant'],
      ['account-bound-grant'],
    ]);
    expect(mountRouteMap).toHaveBeenCalledOnce();
  });
});

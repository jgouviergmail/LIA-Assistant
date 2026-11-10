import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider, initReactI18next } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import { AppConfigSeedContext, type AppConfig } from '@/hooks/useAppConfig';
import { AuthContext } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { loadPlaceMaps, mountPlaceMap } from '@/lib/google-place-map';
import { reportRouteMapLoad } from '@/lib/route-map-metering';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', async original => original<typeof import('react-i18next')>());
vi.mock('@/lib/google-place-map', () => ({ loadPlaceMaps: vi.fn(), mountPlaceMap: vi.fn() }));
const viewport = vi.hoisted(() => ({ narrow: false }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => viewport.narrow }));
vi.mock('@/lib/route-map-metering', async original => ({
  ...(await original<typeof import('@/lib/route-map-metering')>()),
  reportRouteMapLoad: vi.fn(),
}));

const source = { version: 1, label: 'Equator', address: 'A < B & C', position: { lat: 0, lng: 0 } };
function markup(value: object = source) {
  const wire = JSON.stringify(value)
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;')
    .replaceAll('<', '&lt;');
  return `<div class="lia-location-map" data-location-map="${wire}"><img class="lia-route__map-image" src="/api/v1/static-map" alt="Static address map"></div><img class="lia-route__map-image" src="/api/v1/street-view" alt="Street View">`;
}

function expectLoadedImage(name: string) {
  const image = screen.getByRole('img', { name });
  fireEvent.load(image);
  expect(image).toBeVisible();
}
const config: AppConfig = {
  sse: { heartbeat_interval_seconds: 30 },
  rate_limits: { enabled: true, per_minute: 30, burst: 10 },
  i18n: { supported_languages: ['en', 'fr'], default_language: 'en' },
  features: {
    tool_approval_enabled: true,
    attachments_enabled: true,
    rag_spaces_enabled: false,
    rag_spaces_embedding_model: 'none',
    journals_enabled: false,
  },
  place_maps: { enabled: true, estimated_cost_eur: '0.006' },
  api_version: '1',
};
const controller = {
  select: vi.fn(),
  fit: vi.fn(),
  destroy: vi.fn(),
  setRoute: vi.fn(),
  showDetails: vi.fn((_ref: string, content: HTMLElement, header?: HTMLElement) => {
    document.body.append(content);
    if (header) document.body.append(header);
  }),
  clearDetails: vi.fn(),
};
const grant = { api_key: 'public', map_id: 'configured', load_token: 'grant-one' };

async function setup(
  language = 'en',
  seed: AppConfig | null = config,
  owner: string | null = 'a',
  content = markup()
) {
  const i18n = createInstance();
  await i18n.use(initReactI18next).init({
    lng: language,
    fallbackLng: false,
    resources: { en: { translation: en }, fr: { translation: fr } },
    interpolation: { escapeValue: false },
  });
  const tree = (nextOwner = owner, nextContent = content, className?: string) => (
    <I18nextProvider i18n={i18n}>
      <AuthContext.Provider
        value={{
          user: nextOwner ? makeUser({ id: nextOwner }) : null,
          isLoading: false,
          login: vi.fn(),
          verifyMfa: vi.fn(),
          register: vi.fn(),
          logout: vi.fn(),
          initiateGoogleOAuth: vi.fn(),
          completeNativeSignIn: vi.fn(),
          refreshUser: vi.fn(),
          applyUserUpdate: vi.fn(() => true),
        }}
      >
        <AppConfigSeedContext.Provider value={seed}>
          <MarkdownContent content={nextContent} className={className} />
        </AppConfigSeedContext.Provider>
      </AuthContext.Provider>
    </I18nextProvider>
  );
  return { ...renderWithProviders(tree()), tree };
}

beforeEach(() => {
  viewport.narrow = false;
  vi.clearAllMocks();
  vi.mocked(loadPlaceMaps).mockResolvedValue({
    maps: {
      Map: vi.fn(),
      Polyline: vi.fn(),
      LatLngBounds: vi.fn(),
      MapTypeControlStyle: { DROPDOWN_MENU: 1 },
      event: { clearInstanceListeners: vi.fn() },
    },
    marker: { AdvancedMarkerElement: vi.fn(), PinElement: vi.fn() },
  });
  vi.mocked(mountPlaceMap).mockImplementation(
    (_maps, _marker, _element, _data, _id, _select, _failure, construct) => {
      construct();
      return controller;
    }
  );
  vi.mocked(reportRouteMapLoad).mockResolvedValue();
  vi.spyOn(apiClient, 'post').mockResolvedValue(grant);
});

describe('address map from sanitized archived HTML', () => {
  it.each([
    { language: 'en', activate: 'Explore this address', region: 'Interactive address map' },
    {
      language: 'fr',
      activate: 'Explorer cette adresse',
      region: 'Carte interactive de l’adresse',
    },
  ])(
    'names activation and the map in $language without fetching on mount',
    async ({ language, activate, region }) => {
      const view = await setup(language);
      const button = await screen.findByRole('button', { name: activate });
      expectLoadedImage('Static address map');
      expectLoadedImage('Street View');
      expect(screen.getByText(/0,?\.??006/)).toBeVisible();
      expect(apiClient.post).not.toHaveBeenCalled();
      expect(loadPlaceMaps).not.toHaveBeenCalled();
      button.focus();
      await view.user.keyboard('{Enter}');
      expect(await screen.findByRole('region', { name: region })).toBeVisible();
      expect(apiClient.post).toHaveBeenCalledExactlyOnceWith(
        '/connectors/google-maps/load-admissions?purpose=places',
        undefined,
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      );
      expect(reportRouteMapLoad).toHaveBeenCalledExactlyOnceWith('grant-one');
      expectLoadedImage('Street View');
      expect(mountPlaceMap).toHaveBeenCalledOnce();
      expect(vi.mocked(mountPlaceMap).mock.calls[0][3].places[0].position).toEqual({
        lat: 0,
        lng: 0,
      });
    }
  );

  it('opens phone details with keyboard, restores focus and never asks for a route', async () => {
    viewport.narrow = true;
    const view = await setup();
    await view.user.click(await screen.findByRole('button', { name: 'Explore this address' }));
    const choice = await screen.findByRole('button', { name: 'Equator' });
    choice.focus();
    await view.user.keyboard('{Enter}');
    const dialog = await screen.findByRole('dialog', { name: 'Equator' });
    expect(within(dialog).getByRole('heading', { name: 'Equator' })).toHaveFocus();
    expect(within(dialog).getByText('A < B & C')).toBeVisible();
    expect(within(dialog).getByText('0.000000, 0.000000')).toBeVisible();
    expect(within(dialog).getByRole('link', { name: 'Google Maps' })).toHaveAttribute(
      'href',
      'https://www.google.com/maps/search/?api=1&query=0,0'
    );
    expect(within(dialog).queryByText('Route')).toBeNull();
    await view.user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(choice).toHaveFocus();
    expect(apiClient.post).toHaveBeenCalledOnce();
    expect(controller.setRoute).not.toHaveBeenCalled();
  });

  it('keeps the paid instance across wrapper refresh, palette changes and phone/desktop details', async () => {
    viewport.narrow = true;
    const view = await setup();
    await view.user.click(await screen.findByRole('button', { name: 'Explore this address' }));
    await view.user.click(await screen.findByRole('button', { name: 'Equator' }));
    document.documentElement.dataset.theme = 'forest';
    view.rerender(view.tree('a', markup(), 'refreshed'));
    viewport.narrow = false;
    view.rerender(view.tree());
    await waitFor(() => expect(controller.showDetails).toHaveBeenCalled());
    viewport.narrow = true;
    view.rerender(view.tree());
    expect(await screen.findByRole('dialog', { name: 'Equator' })).toBeVisible();
    expect(apiClient.post).toHaveBeenCalledOnce();
    expect(mountPlaceMap).toHaveBeenCalledOnce();
    expect(reportRouteMapLoad).toHaveBeenCalledOnce();
    delete document.documentElement.dataset.theme;
  });

  it.each([
    null,
    { ...config, place_maps: { enabled: false, estimated_cost_eur: '0.006' } },
    { ...config, place_maps: { enabled: true, estimated_cost_eur: '0' } },
    { ...config, place_maps: { enabled: true, estimated_cost_eur: 'NaN' } },
  ])('keeps the static address when the offer is absent or invalid', async seed => {
    await setup('en', seed);
    expectLoadedImage('Static address map');
    expect(screen.queryByRole('button', { name: 'Explore this address' })).toBeNull();
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it('keeps an anonymous or malformed archive inert', async () => {
    const view = await setup('en', config, null);
    expect(screen.queryByRole('button')).toBeNull();
    view.rerender(view.tree('a', markup({ ...source, position: { lat: 91, lng: 0 } })));
    expectLoadedImage('Static address map');
    expect(screen.queryByRole('button')).toBeNull();
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it('retains static media on failed admission, then retries explicitly', async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(new Error('offline'));
    const view = await setup();
    await view.user.click(await screen.findByRole('button', { name: 'Explore this address' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The map is unavailable');
    expectLoadedImage('Static address map');
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
    await view.user.click(screen.getByRole('button', { name: 'Explore this address' }));
    expect(await screen.findByRole('button', { name: 'Equator' })).toBeVisible();
    expect(mountPlaceMap).toHaveBeenCalledOnce();
  });

  it('retries a failed report using its grant without constructing another map', async () => {
    vi.mocked(reportRouteMapLoad).mockRejectedValueOnce(new Error('offline'));
    const view = await setup();
    await view.user.click(await screen.findByRole('button', { name: 'Explore this address' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Load reporting failed');
    await view.user.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(reportRouteMapLoad).toHaveBeenNthCalledWith(2, 'grant-one');
    expect(apiClient.post).toHaveBeenCalledOnce();
    expect(mountPlaceMap).toHaveBeenCalledOnce();
  });

  it('keeps the preview after SDK failure and admits a fresh explicit retry', async () => {
    vi.mocked(loadPlaceMaps).mockRejectedValueOnce(new Error('SDK unavailable'));
    const view = await setup();
    const activate = await screen.findByRole('button', { name: 'Explore this address' });
    await view.user.click(activate);
    expect(await screen.findByRole('alert')).toHaveTextContent('The map is unavailable');
    expectLoadedImage('Static address map');
    expect(activate).toHaveFocus();
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
    await view.user.keyboard('{Enter}');
    expect(await screen.findByRole('button', { name: 'Equator' })).toBeVisible();
    expect(apiClient.post).toHaveBeenCalledTimes(2);
    expect(mountPlaceMap).toHaveBeenCalledOnce();
  });

  it('restores static media and disposes a constructed map when the SDK signals failure', async () => {
    const view = await setup();
    await view.user.click(await screen.findByRole('button', { name: 'Explore this address' }));
    await screen.findByRole('button', { name: 'Equator' });
    act(() => vi.mocked(mountPlaceMap).mock.calls[0][6]());
    expect(await screen.findByRole('alert')).toHaveTextContent('The map is unavailable');
    expectLoadedImage('Static address map');
    expect(controller.destroy).toHaveBeenCalledOnce();
    expect(apiClient.post).toHaveBeenCalledOnce();
  });

  it('aborts and rejects an admission returned after the owner changed', async () => {
    let finish!: (value: typeof grant) => void;
    vi.mocked(apiClient.post).mockReturnValueOnce(
      new Promise(resolve => {
        finish = resolve;
      })
    );
    const view = await setup();
    await view.user.click(await screen.findByRole('button', { name: 'Explore this address' }));
    const signal = vi.mocked(apiClient.post).mock.calls[0][2]?.signal;
    view.rerender(view.tree('b'));
    expect(signal?.aborted).toBe(true);
    await act(async () => finish(grant));
    expect(mountPlaceMap).not.toHaveBeenCalled();
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
    expectLoadedImage('Static address map');
  });

  it('rejects a late SDK result after unmount and tears down a replaced address', async () => {
    let finish!: (value: Awaited<ReturnType<typeof loadPlaceMaps>>) => void;
    const loaded = await vi.mocked(loadPlaceMaps)('public');
    vi.mocked(loadPlaceMaps).mockReturnValueOnce(
      new Promise(resolve => {
        finish = resolve;
      })
    );
    const view = await setup();
    await view.user.click(await screen.findByRole('button', { name: 'Explore this address' }));
    await waitFor(() => expect(loadPlaceMaps).toHaveBeenCalledTimes(2));
    view.unmount();
    await act(async () => finish(loaded));
    expect(mountPlaceMap).not.toHaveBeenCalled();
    const next = await setup();
    await next.user.click(await screen.findByRole('button', { name: 'Explore this address' }));
    await screen.findByRole('button', { name: 'Equator' });
    next.rerender(next.tree('a', markup({ ...source, position: { lat: 1, lng: 0 } })));
    expect(controller.destroy).toHaveBeenCalledOnce();
    expectLoadedImage('Static address map');
  });
});

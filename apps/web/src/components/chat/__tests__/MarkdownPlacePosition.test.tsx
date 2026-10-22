import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/__tests__/test-utils';
import { AppConfigSeedContext, type AppConfig } from '@/hooks/useAppConfig';
import { AuthContext, type User } from '@/lib/auth';
import { apiClient } from '@/lib/api-client';
import { loadPlaceMaps, mountPlaceMap } from '@/lib/google-place-map';
import { reportRouteMapLoad } from '@/lib/route-map-metering';
import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
vi.mock('@/lib/google-place-map', () => ({ loadPlaceMaps: vi.fn(), mountPlaceMap: vi.fn() }));
const viewport = vi.hoisted(() => ({ narrow: false }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => viewport.narrow }));
vi.mock('@/lib/route-map-metering', async original => ({
  ...(await original<typeof import('@/lib/route-map-metering')>()),
  reportRouteMapLoad: vi.fn(),
}));
const wire = JSON.stringify({
  version: 1,
  unlocated_count: 1,
  omitted_count: 0,
  places: [
    {
      ref: 'place_a',
      label: 'East',
      url: 'https://www.google.com/maps/place/?q=a',
      position: { lat: 0, lng: 179.9 },
    },
    {
      ref: 'place_b',
      label: 'Unlocated',
      url: 'https://www.google.com/maps/place/?q=b',
      position: null,
    },
  ],
});
const html = `<div class="lia-place-position" data-place-position="${wire.replaceAll('"', '&quot;')}"><a href="https://www.google.com/maps/">SOURCE_LIST</a></div>`;
const seed: AppConfig = {
  sse: { heartbeat_interval_seconds: 30 },
  rate_limits: { enabled: true, per_minute: 30, burst: 10 },
  i18n: { supported_languages: ['en'], default_language: 'en' },
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
};
function viewTree(owner = 'a', content = html, config: AppConfig | null = seed) {
  const auth = {
    user: { ...user, id: owner },
    isLoading: false,
    login: vi.fn(),
    verifyMfa: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    initiateGoogleOAuth: vi.fn(),
    completeNativeSignIn: vi.fn(),
    refreshUser: vi.fn(),
  };
  return (
    <AuthContext.Provider value={auth}>
      <AppConfigSeedContext.Provider value={config}>
        <MarkdownContent content={content} />
      </AppConfigSeedContext.Provider>
    </AuthContext.Provider>
  );
}
const controller = {
  select: vi.fn(),
  fit: vi.fn(),
  destroy: vi.fn(),
  showDetails: vi.fn(
    (_ref: string, content: HTMLElement, header?: HTMLElement, _onClose?: () => void) => {
      document.body.append(content);
      if (header) document.body.append(header);
    }
  ),
  clearDetails: vi.fn(),
  setRoute: vi.fn(),
};
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
  vi.spyOn(apiClient, 'post').mockResolvedValue({
    api_key: 'public',
    map_id: 'configured',
    load_token: 'grant-one',
  });
});
describe('Position from sanitized archived HTML', () => {
  it('uses a wide phone dialog, returns focus on dismissal and keeps the existing map', async () => {
    viewport.narrow = true;
    vi.mocked(apiClient.post).mockImplementation(async endpoint =>
      endpoint === '/connectors/google-maps/place-route'
        ? {
            origin_source: 'home',
            origin_as_of: null,
            travel_mode: 'WALK',
            polyline: '??_ibE_ibE',
            distance_meters: 1200,
            duration_seconds: 780,
          }
        : { api_key: 'public', map_id: 'configured', load_token: 'grant-one' }
    );
    const view = renderWithProviders(viewTree());
    await view.user.click(
      await screen.findByRole('button', { name: 'chat.position_map.activate' })
    );
    const choice = await screen.findByRole('button', { name: 'East' });
    await view.user.click(choice);
    const dialog = await screen.findByRole('dialog', { name: 'East' });
    expect(within(dialog).getAllByRole('heading', { name: 'East' })).toHaveLength(1);
    expect(within(dialog).getByRole('heading', { name: 'East' })).toHaveFocus();
    expect(await within(dialog).findByText(/chat\.position_map\.route_from_home/)).toBeVisible();
    expect(controller.showDetails).not.toHaveBeenCalled();
    await view.user.click(within(dialog).getByRole('button', { name: 'common.close' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'East' })).toBeNull());
    expect(choice).toHaveFocus();
    await view.user.click(choice);
    expect(await screen.findByRole('dialog', { name: 'East' })).toBeVisible();
    expect(
      vi.mocked(apiClient.post).mock.calls.filter(([url]) => url.endsWith('/place-route'))
    ).toHaveLength(1);
    expect(mountPlaceMap).toHaveBeenCalledOnce();
    expect(reportRouteMapLoad).toHaveBeenCalledOnce();
  });

  it('moves the same selected place between phone and desktop without another route request', async () => {
    viewport.narrow = true;
    const view = renderWithProviders(viewTree());
    await view.user.click(
      await screen.findByRole('button', { name: 'chat.position_map.activate' })
    );
    const choice = await screen.findByRole('button', { name: 'East' });
    await view.user.click(choice);
    expect(await screen.findByRole('dialog', { name: 'East' })).toBeVisible();
    const requests = vi.mocked(apiClient.post).mock.calls.length;
    viewport.narrow = false;
    view.rerender(viewTree());
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'East' })).toBeNull());
    expect(controller.showDetails).toHaveBeenCalledOnce();
    screen.getByRole('button', { name: 'chat.position_map.route_refresh' }).focus();
    viewport.narrow = true;
    view.rerender(viewTree());
    expect(await screen.findByRole('dialog', { name: 'East' })).toBeVisible();
    expect(apiClient.post).toHaveBeenCalledTimes(requests);
    expect(mountPlaceMap).toHaveBeenCalledOnce();
    await view.user.click(screen.getByRole('button', { name: 'common.close' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'East' })).toBeNull());
    expect(choice).toHaveFocus();
  });

  it('does not reopen a natively dismissed desktop place when the viewport becomes a phone', async () => {
    const view = renderWithProviders(viewTree());
    await view.user.click(
      await screen.findByRole('button', { name: 'chat.position_map.activate' })
    );
    await view.user.click(await screen.findByRole('button', { name: 'East' }));
    expect(controller.showDetails).toHaveBeenCalledOnce();
    act(() => controller.showDetails.mock.calls[0][3]?.());
    viewport.narrow = true;
    view.rerender(viewTree());
    expect(screen.queryByRole('dialog', { name: 'East' })).toBeNull();
  });

  it('opens the selected place and draws its route on the already loaded map', async () => {
    vi.mocked(apiClient.post).mockImplementation(async endpoint =>
      endpoint === '/connectors/google-maps/place-route'
        ? {
            origin_source: 'home',
            origin_as_of: null,
            travel_mode: 'WALK',
            polyline: '??_ibE_ibE',
            distance_meters: 0,
            duration_seconds: 0,
          }
        : { api_key: 'public', map_id: 'configured', load_token: 'grant-one' }
    );
    const { user: visitor } = renderWithProviders(viewTree());
    await visitor.click(await screen.findByRole('button', { name: 'chat.position_map.activate' }));
    await visitor.click(await screen.findByRole('button', { name: 'East' }));

    expect(await screen.findByRole('heading', { name: 'East' })).toBeVisible();
    expect(await screen.findByText(/chat\.position_map\.route_from_home/)).toBeVisible();
    await waitFor(() =>
      expect(controller.setRoute).toHaveBeenLastCalledWith(
        expect.objectContaining({
          distance_meters: 0,
          duration_seconds: 0,
        })
      )
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      '/connectors/google-maps/place-route',
      { destination: { lat: 0, lng: 179.9 } },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(mountPlaceMap).toHaveBeenCalledOnce();
    expect(reportRouteMapLoad).toHaveBeenCalledOnce();
  });

  it('preserves the actual backend header and host through Markdown parsing', async () => {
    const reference: { html: string } = JSON.parse(
      readFileSync('../api/tests/unit/domains/agents/display/evolution_card_reference.json', 'utf8')
    );
    const view = renderWithProviders(viewTree('a', reference.html));
    expect(await screen.findByText('Position', { exact: true })).toBeVisible();
    expect(view.container.querySelector('.lia-places-position')).toBeInTheDocument();
    expect(view.container.querySelector('pre')).not.toBeInTheDocument();
    const choices = within(screen.getByRole('list', { name: 'chat.position_map.choose' }));
    expect(choices.getByRole('link', { name: 'Lieu sans coordonnées' })).toBeVisible();
    expect(apiClient.post).not.toHaveBeenCalled();
  });
  it.each([
    null,
    { ...seed, place_maps: { enabled: false } },
    { ...seed, place_maps: { enabled: true, estimated_cost_eur: 'NaN' } },
  ])('never offers an unready or unpriced map', async config => {
    renderWithProviders(viewTree('a', html, config));
    await screen.findByRole('link', { name: 'East' });
    expect(screen.queryByRole('button', { name: 'chat.position_map.activate' })).toBeNull();
    expect(screen.getByText('chat.position_map.unavailable')).toBeVisible();
    expect(document.querySelector('.lia-place-position__stage')).toHaveAttribute(
      'data-available',
      'false'
    );
    expect(apiClient.post).not.toHaveBeenCalled();
  });
  it('preserves international phone and website data through the markdown pipeline', async () => {
    const enriched = JSON.stringify({
      version: 2,
      unlocated_count: 0,
      omitted_count: 0,
      places: [
        {
          ref: 'east',
          label: 'East',
          url: 'https://www.google.com/maps/place/?q=east',
          position: { lat: 0, lng: 179.9 },
          details: {
            address: null,
            rating: null,
            reviews_count: null,
            opening_hours: [],
            phone: '+33102030405',
            website: 'https://east.example.test/?phone=+33102030405',
          },
        },
      ],
    });
    const content = `<div class="lia-place-position" data-place-position="${enriched.replaceAll('"', '&quot;')}">SOURCE_LIST</div>`;
    renderWithProviders(viewTree('a', content));
    fireEvent.click(await screen.findByRole('button', { name: 'chat.position_map.activate' }));
    fireEvent.click(await screen.findByRole('button', { name: 'East' }));
    expect(await screen.findByRole('link', { name: '+33102030405' })).toHaveAttribute(
      'href',
      'tel:+33102030405'
    );
    expect(screen.getByRole('link', { name: 'chat.position_map.website' })).toHaveAttribute(
      'href',
      'https://east.example.test/?phone=+33102030405'
    );
  });
  it('retains the source list and reports no load if native Map construction throws', async () => {
    vi.mocked(mountPlaceMap).mockImplementation(() => {
      throw new Error('Map refused');
    });
    renderWithProviders(viewTree());
    fireEvent.click(await screen.findByRole('button', { name: 'chat.position_map.activate' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('link', { name: 'East' })).toBeVisible();
    expect(screen.getByRole('region', { hidden: true })).not.toBeVisible();
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
  });
  it('renders an automatic offer and list without any admission, SDK or bill before click', async () => {
    renderWithProviders(viewTree());
    await screen.findByRole('button', { name: 'chat.position_map.activate' });
    expect(screen.getByRole('link', { name: 'East' })).toBeVisible();
    expect(screen.getByText('Unlocated')).toBeVisible();
    expect(screen.getByRole('region', { hidden: true })).not.toBeVisible();
    expect(screen.queryByText('chat.position_map.preview')).not.toBeVisible();
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(loadPlaceMaps).not.toHaveBeenCalled();
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
  });
  it('expands only during explicit activation and keeps the canvas measurable for construction', async () => {
    let admit!: (value: { api_key: string; map_id: string; load_token: string }) => void;
    vi.mocked(apiClient.post).mockReturnValue(
      new Promise(resolve => {
        admit = resolve;
      })
    );
    renderWithProviders(viewTree());
    const activate = await screen.findByRole('button', { name: 'chat.position_map.activate' });
    activate.focus();
    fireEvent.click(activate);
    expect(screen.getByRole('region', { hidden: true })).toBeVisible();
    expect(activate).toHaveFocus();
    await act(async () => {
      admit({ api_key: 'public', map_id: 'configured', load_token: 'grant-one' });
    });
    expect(await screen.findByRole('region', { name: 'chat.position_map.map' })).toBeVisible();
    expect(mountPlaceMap).toHaveBeenCalledOnce();
    expect(activate).toHaveFocus();
  });
  it('loads only after explicit costed activation and reports construction once', async () => {
    const view = renderWithProviders(viewTree());
    await view.user.click(
      await screen.findByRole('button', { name: 'chat.position_map.activate' })
    );
    await waitFor(() => expect(mountPlaceMap).toHaveBeenCalledOnce());
    expect(apiClient.post).toHaveBeenCalledWith(
      '/connectors/google-maps/load-admissions?purpose=places',
      undefined,
      expect.anything()
    );
    expect(reportRouteMapLoad).toHaveBeenCalledWith('grant-one');
    expect(controller.select).not.toHaveBeenCalled();
    await view.user.click(screen.getByRole('button', { name: 'East' }));
    expect(controller.select).toHaveBeenCalledWith('place_a');
  });
  it('does not mount or bill a late SDK result after an account switch', async () => {
    let finish!: (value: Awaited<ReturnType<typeof loadPlaceMaps>>) => void;
    vi.mocked(loadPlaceMaps).mockReturnValue(
      new Promise(resolve => {
        finish = resolve;
      })
    );
    const result = renderWithProviders(viewTree());
    fireEvent.click(await screen.findByRole('button', { name: 'chat.position_map.activate' }));
    await waitFor(() => expect(loadPlaceMaps).toHaveBeenCalledOnce());
    result.rerender(viewTree('b'));
    result.rerender(viewTree('a'));
    await act(async () => {
      finish({
        maps: {
          Map: vi.fn(),
          Polyline: vi.fn(),
          LatLngBounds: vi.fn(),
          MapTypeControlStyle: { DROPDOWN_MENU: 1 },
          event: { clearInstanceListeners: vi.fn() },
        },
        marker: { AdvancedMarkerElement: vi.fn(), PinElement: vi.fn() },
      });
    });
    expect(mountPlaceMap).not.toHaveBeenCalled();
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
  });
  it('retries a lost report acknowledgement using the same grant without rebuilding', async () => {
    vi.mocked(reportRouteMapLoad).mockRejectedValueOnce(new Error('ack lost'));
    renderWithProviders(viewTree());
    fireEvent.click(await screen.findByRole('button', { name: 'chat.position_map.activate' }));
    fireEvent.click(await screen.findByRole('button', { name: 'common.retry' }));
    await waitFor(() => expect(reportRouteMapLoad).toHaveBeenCalledTimes(2));
    expect(reportRouteMapLoad).toHaveBeenLastCalledWith('grant-one');
    expect(mountPlaceMap).toHaveBeenCalledOnce();
  });
  it('retains an earlier bill when a later admitted constructor fails before construction', async () => {
    vi.mocked(reportRouteMapLoad).mockRejectedValueOnce(new Error('ack lost'));
    renderWithProviders(viewTree());
    fireEvent.click(await screen.findByRole('button', { name: 'chat.position_map.activate' }));
    await screen.findByRole('button', { name: 'common.retry' });
    act(() => {
      vi.mocked(mountPlaceMap).mock.calls[0][6]();
    });
    vi.mocked(apiClient.post).mockResolvedValue({
      api_key: 'public',
      map_id: 'configured',
      load_token: 'grant-two',
    });
    vi.mocked(mountPlaceMap).mockImplementationOnce(() => {
      throw new Error('no Map constructed');
    });
    fireEvent.click(screen.getByRole('button', { name: 'chat.position_map.activate' }));
    await waitFor(() => expect(mountPlaceMap).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole('button', { name: 'common.retry' }));
    await waitFor(() => expect(reportRouteMapLoad).toHaveBeenCalledTimes(2));
    expect(reportRouteMapLoad).toHaveBeenLastCalledWith('grant-one');
    expect(reportRouteMapLoad).not.toHaveBeenCalledWith('grant-two');
  });
  it('falls back safely on malformed archives or a missing map ID admission', async () => {
    const result = renderWithProviders(
      viewTree(
        'a',
        '<div class="lia-place-position" data-place-position="broken">SOURCE_LIST</div>'
      )
    );
    expect(await screen.findByText('SOURCE_LIST')).toBeVisible();
    expect(screen.queryByRole('button')).toBeNull();
    result.rerender(viewTree());
    vi.mocked(apiClient.post).mockResolvedValue({ api_key: 'public', load_token: 'grant' });
    fireEvent.click(await screen.findByRole('button', { name: 'chat.position_map.activate' }));
    await screen.findByRole('alert');
    expect(loadPlaceMaps).not.toHaveBeenCalled();
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
  });
});
import { readFileSync } from 'node:fs';

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
const controller = { select: vi.fn(), fit: vi.fn(), destroy: vi.fn() };
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(loadPlaceMaps).mockResolvedValue({
    maps: {
      Map: vi.fn(),
      Polyline: vi.fn(),
      LatLngBounds: vi.fn(),
      MapTypeControlStyle: { DROPDOWN_MENU: 1 },
      event: { clearInstanceListeners: vi.fn() },
    },
    marker: { AdvancedMarkerElement: vi.fn() },
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
  it('preserves the actual backend header and host through Markdown parsing', async () => {
    const reference: { html: string } = JSON.parse(
      readFileSync(
        '../api/tests/unit/domains/agents/display/evolution_card_reference.json',
        'utf8'
      )
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
  it('retains the source list and reports no load if native Map construction throws', async () => {
    vi.mocked(mountPlaceMap).mockImplementation(() => {
      throw new Error('Map refused');
    });
    renderWithProviders(viewTree());
    fireEvent.click(await screen.findByRole('button', { name: 'chat.position_map.activate' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('link', { name: 'East' })).toBeVisible();
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
  });
  it('renders an automatic offer and list without any admission, SDK or bill before click', async () => {
    renderWithProviders(viewTree());
    await screen.findByRole('button', { name: 'chat.position_map.activate' });
    expect(screen.getByRole('link', { name: 'East' })).toBeVisible();
    expect(screen.getByText('Unlocated')).toBeVisible();
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(loadPlaceMaps).not.toHaveBeenCalled();
    expect(reportRouteMapLoad).not.toHaveBeenCalled();
  });
  it('loads only after explicit costed activation and reports construction once', async () => {
    renderWithProviders(viewTree());
    fireEvent.click(await screen.findByRole('button', { name: 'chat.position_map.activate' }));
    await waitFor(() => expect(mountPlaceMap).toHaveBeenCalledOnce());
    expect(apiClient.post).toHaveBeenCalledWith(
      '/connectors/google-maps/load-admissions?purpose=places',
      undefined,
      expect.anything()
    );
    expect(reportRouteMapLoad).toHaveBeenCalledWith('grant-one');
    expect(controller.select).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'East' }));
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
        marker: { AdvancedMarkerElement: vi.fn() },
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

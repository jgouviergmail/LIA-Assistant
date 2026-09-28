/**
 * The radio's dashboard card: the header's own command (start from the click,
 * stop on air), the way to the radio's page — and nothing where the radio is
 * not offered.
 */
import { act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { radioPreferences } from '@/lib/radio/__tests__/fixtures';
import { IDLE_RADIO_VIEW, useRadioStore } from '@/stores/radioStore';

const player = vi.hoisted(() => ({
  start: vi.fn(async () => undefined),
  stop: vi.fn(async () => undefined),
}));
vi.mock('@/lib/radio/player', () => ({ radioPlayer: () => player }));

const { api } = vi.hoisted(() => ({ api: { get: vi.fn() } }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));

import { RadioDashboardCard } from '../RadioDashboardCard';

beforeEach(() => {
  vi.clearAllMocks();
  useRadioStore.getState().setView(IDLE_RADIO_VIEW);
  api.get.mockResolvedValue(radioPreferences());
});

describe('RadioDashboardCard', () => {
  it('renders nothing where the radio is not offered', () => {
    const { container } = renderWithProviders(<RadioDashboardCard lng="en" enabled={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('carries the name the listener gave their station, else the language’s', async () => {
    api.get.mockResolvedValue(radioPreferences({ station_name: 'Radio Alex' }));
    renderWithProviders(<RadioDashboardCard lng="en" enabled />);
    expect(await screen.findByRole('heading', { name: 'Radio Alex' })).toBeInTheDocument();
  });

  it('names the station the session on air carries, as the bar above it does', async () => {
    api.get.mockResolvedValue(radioPreferences({ station_name: 'Radio Alex' }));
    renderWithProviders(<RadioDashboardCard lng="en" enabled />);
    // Off air, the listener's own name — which proves their settings arrived.
    expect(await screen.findByRole('heading', { name: 'Radio Alex' })).toBeInTheDocument();
    // On air, the name the session started with (a rename waits for the next one).
    act(() =>
      useRadioStore
        .getState()
        .setView({ ...IDLE_RADIO_VIEW, status: 'playing', stationName: 'Radio Matin' })
    );
    expect(screen.getByRole('heading', { name: 'Radio Matin' })).toBeInTheDocument();
  });

  it('gives the language’s name to a station the listener never named', async () => {
    renderWithProviders(<RadioDashboardCard lng="en" enabled />);
    await vi.waitFor(() => expect(api.get).toHaveBeenCalled());
    // Let the answer land: the name is the language's AFTER the settings arrived.
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByRole('heading', { name: 'radio.station_name' })).toBeInTheDocument();
  });

  it('names the station by its settings again once the session is over, or tuning in', async () => {
    api.get.mockResolvedValue(radioPreferences({ station_name: 'Radio Bob' }));
    // The last session was called « Radio Jean »; the listener renamed it since.
    act(() =>
      useRadioStore
        .getState()
        .setView({ ...IDLE_RADIO_VIEW, status: 'ended', stationName: 'Radio Jean' })
    );
    renderWithProviders(<RadioDashboardCard lng="en" enabled />);
    expect(await screen.findByRole('heading', { name: 'Radio Bob' })).toBeInTheDocument();
    // Tuning in, the session has no name yet: the one it will carry is its settings'.
    act(() => useRadioStore.getState().setView({ ...IDLE_RADIO_VIEW, status: 'starting' }));
    expect(screen.getByRole('heading', { name: 'Radio Bob' })).toBeInTheDocument();
  });

  it('asks nothing where the radio is not offered', () => {
    renderWithProviders(<RadioDashboardCard lng="en" enabled={false} />);
    expect(api.get).not.toHaveBeenCalled();
  });

  it('starts the station from the click and leads to its page', async () => {
    const { user } = renderWithProviders(<RadioDashboardCard lng="en" enabled />);

    await user.click(screen.getByRole('button', { name: 'radio.header.start' }));
    expect(player.start).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('link', { name: 'radio.dashboard.open' })).toHaveAttribute(
      'href',
      '/en/dashboard/radio'
    );
  });

  it('stops the station while it is on air', async () => {
    act(() => useRadioStore.getState().setView({ ...IDLE_RADIO_VIEW, status: 'playing' }));
    const { user } = renderWithProviders(<RadioDashboardCard lng="en" enabled />);

    await user.click(screen.getByRole('button', { name: 'radio.header.stop' }));
    expect(player.stop).toHaveBeenCalledTimes(1);
    expect(player.start).not.toHaveBeenCalled();
  });
});

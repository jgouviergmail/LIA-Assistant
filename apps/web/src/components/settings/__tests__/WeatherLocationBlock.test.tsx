/**
 * WeatherLocationBlock — the opt-in toggle (persist + refresh + toast in both
 * directions and the error path), the geolocation-required hint, and the
 * stored-location transparency panel (populated vs empty) with its clear action.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { useGeolocation } = vi.hoisted(() => ({ useGeolocation: vi.fn() }));
vi.mock('@/hooks/useGeolocation', () => ({ useGeolocation }));
const { get, patch, put } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), put: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get, patch, put } }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}));

import { WeatherLocationBlock } from '../WeatherLocationBlock';

type Coords = { lat: number; lon: number; accuracy: number | null; timestamp: number };

function authed(over: Partial<User> = {}) {
  return { user: makeUser(over), refreshUser: vi.fn() };
}

// The component reads only `coordinates` and `isEnabled` off useGeolocation.
function geo(coordinates: Coords | null, isEnabled: boolean) {
  return { coordinates, isEnabled };
}

const NO_LOCATION = {
  stored: false,
  lat: null,
  lon: null,
  accuracy: null,
  updated_at: null,
  stale: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  get.mockResolvedValue(NO_LOCATION);
  // Default: geolocation off + no coordinates → the throttled push effect never fires.
  useGeolocation.mockReturnValue(geo(null, false));
});

describe('WeatherLocationBlock — toggle', () => {
  it('is off and hides the transparency panel when not opted in', () => {
    useAuth.mockReturnValue(authed({ weather_use_last_known_location: false }));
    renderWithProviders(<WeatherLocationBlock lng="en" />);
    expect(screen.getByRole('switch')).not.toBeChecked();
    expect(screen.queryByText('heartbeat.weather_location.stored_title')).not.toBeInTheDocument();
  });

  it('enabling persists the preference, refreshes and toasts', async () => {
    const ctx = authed({ weather_use_last_known_location: false });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<WeatherLocationBlock lng="en" />);
    await user.click(screen.getByRole('switch'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/weather-location-preference', { enabled: true })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('toasts an error when the toggle request fails', async () => {
    patch.mockRejectedValue(new Error('boom'));
    useAuth.mockReturnValue(authed({ weather_use_last_known_location: false }));
    const { user } = renderWithProviders(<WeatherLocationBlock lng="en" />);
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});

describe('WeatherLocationBlock — opted in', () => {
  it('warns that geolocation is required when it is disabled', async () => {
    useAuth.mockReturnValue(authed({ weather_use_last_known_location: true }));
    useGeolocation.mockReturnValue(geo(null, false));
    renderWithProviders(<WeatherLocationBlock lng="en" />);
    expect(
      await screen.findByText('heartbeat.weather_location.geoloc_required_hint')
    ).toBeInTheDocument();
  });

  it('shows the stored coordinates and clears them on demand', async () => {
    get.mockResolvedValue({
      stored: true,
      lat: 48.8566,
      lon: 2.3522,
      accuracy: 12,
      updated_at: '2026-07-01T10:00:00Z',
      stale: false,
    });
    useAuth.mockReturnValue(authed({ weather_use_last_known_location: true }));
    const { user } = renderWithProviders(<WeatherLocationBlock lng="en" />);
    expect(await screen.findByText('48.8566, 2.3522')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /clear_button/i }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/weather-location-preference', { enabled: false })
    );
  });

  it('shows the empty state when no location is stored', async () => {
    get.mockResolvedValue(NO_LOCATION);
    useAuth.mockReturnValue(authed({ weather_use_last_known_location: true }));
    renderWithProviders(<WeatherLocationBlock lng="en" />);
    expect(await screen.findByText('heartbeat.weather_location.no_stored')).toBeInTheDocument();
  });
});

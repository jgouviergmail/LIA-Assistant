/**
 * LastKnownLocationSection — the generalized last-known location opt-in that
 * lives on the Google Places connector (moved from the proactive-notifications
 * weather block, 2026-08-16): toggle persist + refresh + toast in both
 * directions and the error path, the geolocation-required hint, and the
 * stored-location transparency panel (populated vs empty) with its clear
 * action. The throttled backend push is NOT here — it belongs to the global
 * useLastKnownLocationSync hook, independent of any settings page being open.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { useGeolocation } = vi.hoisted(() => ({ useGeolocation: vi.fn() }));
vi.mock('@/hooks/useGeolocation', () => ({ useGeolocation }));
const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get, patch } }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}));

import { LastKnownLocationSection } from '../LastKnownLocationSection';

function authed(over: Partial<User> = {}) {
  return { user: makeUser(over), refreshUser: vi.fn() };
}

const NO_LOCATION = {
  stored: false,
  lat: null,
  lon: null,
  accuracy: null,
  updated_at: null,
  stale: false,
};

const t = (key: string) => key;

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  get.mockResolvedValue(NO_LOCATION);
  useGeolocation.mockReturnValue({ isEnabled: false });
});

describe('LastKnownLocationSection — toggle', () => {
  it('is off and hides the transparency panel when not opted in', () => {
    useAuth.mockReturnValue(authed({ use_last_known_location: false }));
    renderWithProviders(<LastKnownLocationSection t={t} />);
    expect(screen.getByRole('switch')).not.toBeChecked();
    expect(
      screen.queryByText('settings.location.last_known.stored_title')
    ).not.toBeInTheDocument();
  });

  it('enabling persists the preference, refreshes and toasts', async () => {
    const ctx = authed({ use_last_known_location: false });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<LastKnownLocationSection t={t} />);
    await user.click(screen.getByRole('switch'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/location-preference', { enabled: true })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('toasts an error when the toggle request fails', async () => {
    patch.mockRejectedValue(new Error('boom'));
    useAuth.mockReturnValue(authed({ use_last_known_location: false }));
    const { user } = renderWithProviders(<LastKnownLocationSection t={t} />);
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});

describe('LastKnownLocationSection — opted in', () => {
  it('warns that geolocation is required when it is disabled', async () => {
    useAuth.mockReturnValue(authed({ use_last_known_location: true }));
    useGeolocation.mockReturnValue({ isEnabled: false });
    renderWithProviders(<LastKnownLocationSection t={t} />);
    expect(
      await screen.findByText('settings.location.last_known.geoloc_required_hint')
    ).toBeInTheDocument();
  });

  it('does not warn when geolocation is enabled', async () => {
    useAuth.mockReturnValue(authed({ use_last_known_location: true }));
    useGeolocation.mockReturnValue({ isEnabled: true });
    renderWithProviders(<LastKnownLocationSection t={t} />);
    await screen.findByText('settings.location.last_known.no_stored');
    expect(
      screen.queryByText('settings.location.last_known.geoloc_required_hint')
    ).not.toBeInTheDocument();
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
    useAuth.mockReturnValue(authed({ use_last_known_location: true }));
    const { user } = renderWithProviders(<LastKnownLocationSection t={t} />);
    expect(await screen.findByText('48.8566, 2.3522')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /clear_button/i }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/location-preference', { enabled: false })
    );
  });

  it('flags a stale stored position', async () => {
    get.mockResolvedValue({
      stored: true,
      lat: 48.8566,
      lon: 2.3522,
      accuracy: 12,
      updated_at: '2026-07-01T10:00:00Z',
      stale: true,
    });
    useAuth.mockReturnValue(authed({ use_last_known_location: true }));
    renderWithProviders(<LastKnownLocationSection t={t} />);
    expect(
      await screen.findByText('settings.location.last_known.stored_stale')
    ).toBeInTheDocument();
  });

  it('shows the empty state when no location is stored', async () => {
    get.mockResolvedValue(NO_LOCATION);
    useAuth.mockReturnValue(authed({ use_last_known_location: true }));
    renderWithProviders(<LastKnownLocationSection t={t} />);
    expect(
      await screen.findByText('settings.location.last_known.no_stored')
    ).toBeInTheDocument();
  });
});

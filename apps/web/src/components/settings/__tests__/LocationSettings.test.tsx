/**
 * LocationSettings — the standalone Location section: the geolocation toggle
 * (granted / refused / disable), the permission surfaces (unsupported, denied
 * help, hook error), and the home location CRUD with its **optimistic cache
 * update** (`setData` after the PUT/DELETE mutations) plus both failure paths.
 * Moved out of the Google Places connector card (2026-08): the section now
 * renders inside its own titled `SettingsSection` card.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { mutationResult, mutateSpy } from '@/__tests__/api-mocks';
import type { useGeolocation as useGeolocationFn } from '@/hooks/useGeolocation';
import type { HomeLocation } from '../LocationSettings';

const { useGeolocation } = vi.hoisted(() => ({ useGeolocation: vi.fn() }));
vi.mock('@/hooks/useGeolocation', () => ({ useGeolocation }));
const { useApplicationAccountQuery } = vi.hoisted(() => ({ useApplicationAccountQuery: vi.fn() }));
vi.mock('@/hooks/useApplicationAccountQuery', () => ({ useApplicationAccountQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));
const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() },
}));
// The child owns its own suite (LastKnownLocationSection.test.tsx); here only
// the parent's contract matters: the section is mounted between geolocation
// and home, with the shared `t`.
vi.mock('../LastKnownLocationSection', () => ({
  LastKnownLocationSection: () => <div data-testid="last-known-location-section" />,
}));

import { LocationSettings } from '../LocationSettings';

const HOME_ENDPOINT = '/users/me/home-location';

type GeoHook = ReturnType<typeof useGeolocationFn>;

function geo(over: Partial<GeoHook> = {}) {
  return {
    permission: 'granted' as GeoHook['permission'],
    isEnabled: false,
    isLoading: false,
    error: null,
    coordinates: null,
    enable: vi.fn().mockResolvedValue({ lat: 1, lon: 2, accuracy: 5, timestamp: 0 }),
    disable: vi.fn(),
    refresh: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

/** Captured per test so assertions can target the right mutation. */
let putMutate: ReturnType<typeof mutateSpy>;
let deleteMutate: ReturnType<typeof mutateSpy>;
let persistedHome: HomeLocation | null;
const refetchHome = vi.fn(async () => {});

function stubHome(data: HomeLocation | null) {
  persistedHome = data;
  useApplicationAccountQuery.mockImplementation(() => ({ data: persistedHome, ownerId: 'one', refetch: refetchHome }));
}

beforeEach(() => {
  vi.clearAllMocks();
  useGeolocation.mockReturnValue(geo());
  stubHome(null);
  putMutate = mutateSpy().mockImplementation(async () => {
    persistedHome = { address: '10 Downing St', lat: 51.5, lon: -0.12 };
    return persistedHome;
  });
  deleteMutate = mutateSpy().mockImplementation(async () => { persistedHome = null; });
  // The component instantiates two mutations; route them by HTTP method.
  useApiMutation.mockImplementation((opts: { method: string }) =>
    opts.method === 'PUT'
      ? mutationResult({ mutate: putMutate })
      : mutationResult({ mutate: deleteMutate })
  );
});

describe('LocationSettings — standalone section', () => {
  it('renders as a titled section card with the shell anchor', () => {
    renderWithProviders(<LocationSettings lng="en" />);
    expect(screen.getByText('settings.location.title')).toBeInTheDocument();
    expect(screen.getByText('settings.location.description')).toBeInTheDocument();
    expect(document.getElementById('settings-section-location')).not.toBeNull();
  });
});

describe('LocationSettings — geolocation', () => {
  it('enabling a granted geolocation confirms success', async () => {
    const enable = vi.fn().mockResolvedValue({ lat: 1, lon: 2, accuracy: 5, timestamp: 0 });
    useGeolocation.mockReturnValue(geo({ isEnabled: false, enable }));
    const { user } = renderWithProviders(<LocationSettings lng="en" />);
    await user.click(screen.getByRole('switch'));
    expect(enable).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('settings.location.geolocation.enabled')
    );
  });

  it('reports a refused permission instead of a success', async () => {
    useGeolocation.mockReturnValue(
      geo({ isEnabled: false, enable: vi.fn().mockResolvedValue(null) })
    );
    const { user } = renderWithProviders(<LocationSettings lng="en" />);
    await user.click(screen.getByRole('switch'));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.location.geolocation.permission_denied')
    );
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('disabling geolocation calls disable and informs the user', async () => {
    const disable = vi.fn();
    useGeolocation.mockReturnValue(geo({ isEnabled: true, disable }));
    const { user } = renderWithProviders(<LocationSettings lng="en" />);
    await user.click(screen.getByRole('switch'));
    expect(disable).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith('settings.location.geolocation.disabled')
    );
  });

  it('locks the toggle when geolocation is unsupported', () => {
    useGeolocation.mockReturnValue(geo({ permission: 'unsupported' }));
    renderWithProviders(<LocationSettings lng="en" />);
    expect(screen.getByRole('switch')).toBeDisabled();
  });

  it('explains how to recover from a denied permission', () => {
    useGeolocation.mockReturnValue(geo({ permission: 'denied' }));
    renderWithProviders(<LocationSettings lng="en" />);
    expect(screen.getByText('settings.location.geolocation.denied_help')).toBeInTheDocument();
  });

  it('surfaces a geolocation hook error', () => {
    useGeolocation.mockReturnValue(geo({ error: 'GPS unavailable' }));
    renderWithProviders(<LocationSettings lng="en" />);
    expect(screen.getByText('GPS unavailable')).toBeInTheDocument();
  });
});

describe('LocationSettings — last-known location', () => {
  it('mounts the last-known section with its title, between geolocation and home', () => {
    renderWithProviders(<LocationSettings lng="en" />);
    expect(screen.getByText('settings.location.last_known.title')).toBeInTheDocument();
    expect(screen.getByTestId('last-known-location-section')).toBeInTheDocument();
  });
});

describe('LocationSettings — home location', () => {
  it('preserves a focused unsaved address when a confirmed native address arrives', async () => {
    const { user, rerender } = renderWithProviders(<LocationSettings lng="en" />);
    const input = screen.getByPlaceholderText('settings.location.home.placeholder');
    await user.type(input, 'My unsaved address');
    stubHome({ address: 'Confirmed address', lat: 4, lon: 5 });
    rerender(<LocationSettings lng="en" />);
    expect(screen.getByText('Confirmed address')).toBeInTheDocument();
    expect(input).toBeInTheDocument();
    expect(input).toHaveValue('My unsaved address');
    expect(input).toHaveFocus();
  });
  it('keeps save disabled while the address is blank', async () => {
    const { user } = renderWithProviders(<LocationSettings lng="en" />);
    const save = screen.getByRole('button', { name: 'common.save' });
    expect(save).toBeDisabled();
    // Whitespace only is still blank once trimmed.
    await user.type(screen.getByPlaceholderText('settings.location.home.placeholder'), '   ');
    expect(save).toBeDisabled();
    expect(putMutate).not.toHaveBeenCalled();
  });

  it('saves the address, primes the cache optimistically and clears the input', async () => {
    const { user } = renderWithProviders(<LocationSettings lng="en" />);
    const input = screen.getByPlaceholderText('settings.location.home.placeholder');
    await user.type(input, '10 Downing St');
    await user.click(screen.getByRole('button', { name: 'common.save' }));
    await waitFor(() =>
      expect(putMutate).toHaveBeenCalledWith(HOME_ENDPOINT, {
        address: '10 Downing St',
        lat: 0,
        lon: 0,
      })
    );
    expect(screen.getByText('10 Downing St')).toBeInTheDocument();
    expect(refetchHome).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith('settings.location.home.saved');
    expect(input).not.toBeInTheDocument();
  });

  it('reports a save failure and leaves the cache untouched', async () => {
    putMutate.mockRejectedValue(new Error('boom'));
    const { user } = renderWithProviders(<LocationSettings lng="en" />);
    await user.type(
      screen.getByPlaceholderText('settings.location.home.placeholder'),
      '10 Downing St'
    );
    await user.click(screen.getByRole('button', { name: 'common.save' }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.location.home.save_error')
    );
    expect(screen.queryByText('10 Downing St')).not.toBeInTheDocument();
  });

  it('shows the stored address and clears it optimistically', async () => {
    stubHome({ address: '10 Downing St', lat: 51.5, lon: -0.12 });
    const { user, rerender } = renderWithProviders(<LocationSettings lng="en" />);
    expect(screen.getByText('10 Downing St')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'common.delete' }));
    await waitFor(() => expect(deleteMutate).toHaveBeenCalledWith(HOME_ENDPOINT, undefined));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('settings.location.home.cleared'));
    rerender(<LocationSettings lng="en" />);
    await waitFor(() => expect(screen.queryByText('10 Downing St')).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith('settings.location.home.cleared');
  });

  it('reports a clear failure and leaves the cache untouched', async () => {
    stubHome({ address: '10 Downing St', lat: 51.5, lon: -0.12 });
    deleteMutate.mockRejectedValue(new Error('boom'));
    const { user } = renderWithProviders(<LocationSettings lng="en" />);
    await user.click(screen.getByRole('button', { name: 'common.delete' }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.location.home.clear_error')
    );
    expect(screen.getByText('10 Downing St')).toBeInTheDocument();
  });
});

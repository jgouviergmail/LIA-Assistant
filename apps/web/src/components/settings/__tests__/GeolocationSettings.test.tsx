/**
 * GeolocationSettings — the enable/disable switch (permission grant vs denial),
 * the manual refresh, and the permission badge.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useGeolocation } = vi.hoisted(() => ({ useGeolocation: vi.fn() }));
vi.mock('@/hooks/useGeolocation', () => ({ useGeolocation }));
const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() },
}));

import { GeolocationSettings } from '../GeolocationSettings';
import type { useGeolocation as useGeolocationFn } from '@/hooks/useGeolocation';

type GeoHook = ReturnType<typeof useGeolocationFn>;

function hook(over: Partial<GeoHook> = {}) {
  return {
    coordinates: null,
    permission: 'prompt',
    isEnabled: false,
    isLoading: false,
    error: null,
    enable: vi.fn().mockResolvedValue({ latitude: 1, longitude: 2 }),
    disable: vi.fn(),
    refresh: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

beforeEach(() => vi.clearAllMocks());

describe('GeolocationSettings', () => {
  it('enabling geolocation that is granted toasts success', async () => {
    const enable = vi.fn().mockResolvedValue({ latitude: 1, longitude: 2 });
    useGeolocation.mockReturnValue(hook({ isEnabled: false, enable }));
    const { user } = renderWithProviders(<GeolocationSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('switch'));
    expect(enable).toHaveBeenCalled();
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
  });

  it('enabling geolocation that is denied toasts an error', async () => {
    const enable = vi.fn().mockResolvedValue(null);
    useGeolocation.mockReturnValue(hook({ isEnabled: false, enable }));
    const { user } = renderWithProviders(<GeolocationSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });

  it('disabling geolocation calls disable and toasts info', async () => {
    const disable = vi.fn();
    useGeolocation.mockReturnValue(hook({ isEnabled: true, permission: 'granted', disable }));
    const { user } = renderWithProviders(<GeolocationSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('switch'));
    expect(disable).toHaveBeenCalled();
    await waitFor(() => expect(toast.info).toHaveBeenCalledTimes(1));
  });

  it('refreshing with coordinates present toasts success', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    useGeolocation.mockReturnValue(
      hook({
        isEnabled: true,
        permission: 'granted',
        coordinates: { lat: 1, lon: 2, accuracy: 10, timestamp: 0 },
        refresh,
      })
    );
    const { user } = renderWithProviders(<GeolocationSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('button', { name: /refresh/i }));
    expect(refresh).toHaveBeenCalled();
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
  });

  it('shows the granted permission badge', () => {
    useGeolocation.mockReturnValue(hook({ permission: 'granted' }));
    renderWithProviders(<GeolocationSettings lng="en" collapsible={false} />);
    expect(
      screen.getByText('settings.location.geolocation.permission_granted')
    ).toBeInTheDocument();
  });
});

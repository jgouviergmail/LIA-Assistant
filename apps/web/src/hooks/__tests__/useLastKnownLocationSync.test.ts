/**
 * useLastKnownLocationSync — the global throttled push of the browser
 * position to PUT /auth/me/last-location.
 *
 * Before 2026-08-16 the push lived inside the weather settings block, so it
 * only ran while that settings page was open — in real mobility nothing fed
 * the backend. The hook now lives in the authenticated shell: it pushes
 * whenever fresh coordinates exist, the user opted in, and the 30-minute
 * client throttle has elapsed (the server enforces its own 30-minute floor
 * on top). A failed push must NOT stamp the throttle — silence for 30
 * minutes after a transient error would be self-inflicted.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';
import {
  LAST_LOCATION_PUSH_THROTTLE_MS,
  LAST_LOCATION_PUSH_TS_KEY,
} from '@/lib/constants';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { useGeolocation } = vi.hoisted(() => ({ useGeolocation: vi.fn() }));
vi.mock('@/hooks/useGeolocation', () => ({ useGeolocation }));
const { put } = vi.hoisted(() => ({ put: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { put } }));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { useLastKnownLocationSync } from '../useLastKnownLocationSync';

const COORDS = { lat: 43.6045, lon: 1.4442, accuracy: 25, timestamp: Date.now() };

function authed(over: Partial<User> = {}) {
  return { user: makeUser({ use_last_known_location: true, ...over }) };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  put.mockResolvedValue({ updated: true, throttled: false });
  useAuth.mockReturnValue(authed());
  useGeolocation.mockReturnValue({ coordinates: COORDS, isEnabled: true });
});

describe('useLastKnownLocationSync', () => {
  it('pushes the position and stamps the throttle marker', async () => {
    renderHook(() => useLastKnownLocationSync());

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith('/auth/me/last-location', {
        lat: COORDS.lat,
        lon: COORDS.lon,
        accuracy: COORDS.accuracy,
      })
    );
    await waitFor(() => expect(localStorage.getItem(LAST_LOCATION_PUSH_TS_KEY)).not.toBeNull());
  });

  it('respects the client-side throttle window', async () => {
    localStorage.setItem(LAST_LOCATION_PUSH_TS_KEY, String(Date.now()));
    renderHook(() => useLastKnownLocationSync());
    await new Promise(r => setTimeout(r, 0));
    expect(put).not.toHaveBeenCalled();
  });

  it('pushes again once the throttle window has elapsed', async () => {
    localStorage.setItem(
      LAST_LOCATION_PUSH_TS_KEY,
      String(Date.now() - LAST_LOCATION_PUSH_THROTTLE_MS - 1000)
    );
    renderHook(() => useLastKnownLocationSync());
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
  });

  it('stays inert when the user has not opted in', async () => {
    useAuth.mockReturnValue(authed({ use_last_known_location: false }));
    renderHook(() => useLastKnownLocationSync());
    await new Promise(r => setTimeout(r, 0));
    expect(put).not.toHaveBeenCalled();
  });

  it('stays inert while browser geolocation is disabled or has no coordinates', async () => {
    useGeolocation.mockReturnValue({ coordinates: null, isEnabled: true });
    const { unmount } = renderHook(() => useLastKnownLocationSync());
    await new Promise(r => setTimeout(r, 0));
    expect(put).not.toHaveBeenCalled();
    unmount();

    useGeolocation.mockReturnValue({ coordinates: COORDS, isEnabled: false });
    renderHook(() => useLastKnownLocationSync());
    await new Promise(r => setTimeout(r, 0));
    expect(put).not.toHaveBeenCalled();
  });

  it('does not stamp the throttle when the push fails, so the next change retries', async () => {
    put.mockRejectedValue(new Error('network down'));
    renderHook(() => useLastKnownLocationSync());
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(localStorage.getItem(LAST_LOCATION_PUSH_TS_KEY)).toBeNull();
  });

  it('cleans up the legacy weather-scoped throttle marker', async () => {
    localStorage.setItem('smart_weather_last_push_ms', '12345');
    renderHook(() => useLastKnownLocationSync());
    await waitFor(() =>
      expect(localStorage.getItem('smart_weather_last_push_ms')).toBeNull()
    );
  });
});

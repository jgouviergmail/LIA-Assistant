/**
 * Unit tests for `useGeolocation` (audit F010, risk-first).
 *
 * Drives the browser-geolocation hook with stubbed `navigator.geolocation` /
 * `navigator.permissions` and the real jsdom `localStorage`. Covers the
 * unsupported path, enable→success (coords + cache write), the three
 * getCurrentPosition error codes (denied / position-unavailable / timeout with
 * their permission mapping), disable (cache clear), cached-coordinate loading
 * (valid + expired), and refresh gating on the enabled flag.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { useGeolocation } from '../useGeolocation';

const getCurrentPosition = vi.fn();
const permissionsQuery = vi.fn();

/** Configure navigator.geolocation / navigator.permissions for a test. */
function stubNavigator(opts: { geolocation?: boolean; permissions?: boolean } = {}) {
  const { geolocation = true, permissions = true } = opts;
  Object.defineProperty(navigator, 'geolocation', {
    configurable: true,
    value: geolocation ? { getCurrentPosition } : undefined,
  });
  Object.defineProperty(navigator, 'permissions', {
    configurable: true,
    value: permissions ? { query: permissionsQuery } : undefined,
  });
}

function positionOf(lat: number, lon: number, accuracy = 10) {
  return { coords: { latitude: lat, longitude: lon, accuracy } };
}

/**
 * Flush a full macrotask so the async mount effects (initialize →
 * checkPermission → setState) fully settle before we act. Without this the
 * mount's `setState({ permission: 'prompt' })` can land AFTER enable() and
 * clobber the result — a race that never happens in a real browser where the
 * mount settles before any user interaction.
 */
const settle = () => act(async () => new Promise(r => setTimeout(r, 0)));

// GeolocationPositionError codes (constants the hook switches on).
const ERR = { PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 };

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  stubNavigator();
  permissionsQuery.mockResolvedValue({
    state: 'prompt',
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
});
afterEach(() => {
  vi.clearAllMocks();
});

describe('useGeolocation', () => {
  it('reports unsupported when navigator.geolocation is absent', async () => {
    stubNavigator({ geolocation: false, permissions: false });
    const { result } = renderHook(() => useGeolocation());
    await waitFor(() => expect(result.current.permission).toBe('unsupported'));
  });

  it('enable() persists the preference, requests a position and exposes coords', async () => {
    getCurrentPosition.mockImplementation(success => success(positionOf(48.85, 2.35, 12)));
    const { result } = renderHook(() => useGeolocation());
    await settle();

    await act(async () => {
      await result.current.enable();
    });

    expect(localStorage.getItem('geolocation_enabled')).toBe('true');
    expect(result.current.coordinates).toMatchObject({ lat: 48.85, lon: 2.35, accuracy: 12 });
    expect(result.current.permission).toBe('granted');
    // Coordinates are cached for quick re-use.
    expect(localStorage.getItem('geolocation_cache')).toContain('48.85');
  });

  it('maps PERMISSION_DENIED to a denied permission with no coords', async () => {
    getCurrentPosition.mockImplementation((_ok, err) =>
      err({ code: ERR.PERMISSION_DENIED, ...ERR })
    );
    const { result } = renderHook(() => useGeolocation());
    await settle();
    await act(async () => {
      await result.current.enable();
    });
    expect(result.current.permission).toBe('denied');
    expect(result.current.coordinates).toBeNull();
    expect(result.current.error).toBe('Permission denied');
  });

  it('keeps permission granted when the position is merely unavailable', async () => {
    getCurrentPosition.mockImplementation((_ok, err) =>
      err({ code: ERR.POSITION_UNAVAILABLE, ...ERR })
    );
    const { result } = renderHook(() => useGeolocation());
    await settle();
    await act(async () => {
      await result.current.enable();
    });
    expect(result.current.permission).toBe('granted');
    expect(result.current.error).toBe('Position unavailable');
  });

  it('disable() clears the preference, cache and coordinates', async () => {
    getCurrentPosition.mockImplementation(success => success(positionOf(1, 2)));
    const { result } = renderHook(() => useGeolocation());
    await settle();
    await act(async () => {
      await result.current.enable();
    });
    expect(result.current.coordinates).not.toBeNull();

    act(() => {
      result.current.disable();
    });
    expect(localStorage.getItem('geolocation_enabled')).toBe('false');
    expect(localStorage.getItem('geolocation_cache')).toBeNull();
    expect(result.current.coordinates).toBeNull();
  });

  it('loads still-valid cached coordinates on mount', async () => {
    localStorage.setItem(
      'geolocation_cache',
      JSON.stringify({ lat: 10, lon: 20, accuracy: 5, timestamp: Date.now() })
    );
    const { result } = renderHook(() => useGeolocation());
    await waitFor(() => expect(result.current.coordinates).toMatchObject({ lat: 10, lon: 20 }));
  });

  it('ignores expired cached coordinates', async () => {
    localStorage.setItem(
      'geolocation_cache',
      JSON.stringify({ lat: 10, lon: 20, accuracy: 5, timestamp: Date.now() - 10 * 60 * 1000 })
    );
    const { result } = renderHook(() => useGeolocation());
    // Give the mount effect a tick; coords must remain null (cache too old).
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.coordinates).toBeNull();
  });

  it('refresh() is a no-op while geolocation is disabled', async () => {
    const { result } = renderHook(() => useGeolocation());
    await act(async () => {
      await Promise.resolve();
    });
    getCurrentPosition.mockClear();
    await act(async () => {
      await result.current.refresh();
    });
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });
});

/**
 * PWA lifecycle (2026-08-16): a frozen-then-resumed PWA used to keep a dead
 * hook state forever — coordinates expired, nothing refreshed, every chat
 * message shipped `geolocation: null` and the backend fell back to home.
 * The hook now reacts to `visibilitychange`/`pageshow`.
 */
describe('useGeolocation — PWA lifecycle', () => {
  function fireVisible() {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
    document.dispatchEvent(new Event('visibilitychange'));
  }

  it('refreshes silently on return-to-foreground when granted and the cache is gone', async () => {
    localStorage.setItem('geolocation_enabled', 'true');
    permissionsQuery.mockResolvedValue({
      state: 'granted',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
    getCurrentPosition.mockImplementation(success => success(positionOf(43.6, 1.44)));
    const { result } = renderHook(() => useGeolocation());
    await settle();
    // Simulate the frozen period: the cached position has been purged.
    localStorage.removeItem('geolocation_cache');
    getCurrentPosition.mockClear();

    await act(async () => {
      fireVisible();
      await new Promise(r => setTimeout(r, 0));
    });

    expect(getCurrentPosition).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(result.current.coordinates).toMatchObject({ lat: 43.6 }));
  });

  it('does not touch the GPS when the cached position is still fresh', async () => {
    localStorage.setItem('geolocation_enabled', 'true');
    localStorage.setItem(
      'geolocation_cache',
      JSON.stringify({ lat: 10, lon: 20, accuracy: 5, timestamp: Date.now() })
    );
    permissionsQuery.mockResolvedValue({
      state: 'granted',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
    // The mount itself refreshes (enabled + granted); only count events
    // fired AFTER the mount has settled.
    getCurrentPosition.mockImplementation(success => success(positionOf(10, 20)));
    renderHook(() => useGeolocation());
    await settle();
    getCurrentPosition.mockClear();

    await act(async () => {
      fireVisible();
      await new Promise(r => setTimeout(r, 0));
    });

    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  it('stays inert on return-to-foreground while the user has not opted in', async () => {
    localStorage.setItem('geolocation_enabled', 'false');
    renderHook(() => useGeolocation());
    await settle();
    getCurrentPosition.mockClear();

    await act(async () => {
      fireVisible();
      await new Promise(r => setTimeout(r, 0));
    });

    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  it('flags needsReactivation instead of calling the GPS when the permission fell back to prompt', async () => {
    // iOS standalone drops the grant after a while: enabled=true but the
    // permission is 'prompt' again — only a user gesture can reopen the
    // native sheet, so the hook must NOT fire getCurrentPosition itself.
    localStorage.setItem('geolocation_enabled', 'true');
    permissionsQuery.mockResolvedValue({
      state: 'prompt',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
    const { result } = renderHook(() => useGeolocation());
    await settle();
    getCurrentPosition.mockClear();

    await act(async () => {
      fireVisible();
      await new Promise(r => setTimeout(r, 0));
    });

    expect(getCurrentPosition).not.toHaveBeenCalled();
    expect(result.current.needsReactivation).toBe(true);
  });

  it('does not claim reactivation when geolocation was never enabled', async () => {
    localStorage.setItem('geolocation_enabled', 'false');
    const { result } = renderHook(() => useGeolocation());
    await settle();
    expect(result.current.needsReactivation).toBe(false);
  });

  it('does not claim reactivation while the permission is granted', async () => {
    localStorage.setItem('geolocation_enabled', 'true');
    permissionsQuery.mockResolvedValue({
      state: 'granted',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
    getCurrentPosition.mockImplementation(success => success(positionOf(1, 2)));
    const { result } = renderHook(() => useGeolocation());
    await settle();
    expect(result.current.needsReactivation).toBe(false);
  });

  it('pageshow with persisted=true (bfcache restore) triggers the same refresh path', async () => {
    localStorage.setItem('geolocation_enabled', 'true');
    permissionsQuery.mockResolvedValue({
      state: 'granted',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
    getCurrentPosition.mockImplementation(success => success(positionOf(43.6, 1.44)));
    renderHook(() => useGeolocation());
    await settle();
    localStorage.removeItem('geolocation_cache');
    getCurrentPosition.mockClear();

    await act(async () => {
      const restore = new Event('pageshow');
      Object.defineProperty(restore, 'persisted', { value: true });
      window.dispatchEvent(restore);
      await new Promise(r => setTimeout(r, 0));
    });

    expect(getCurrentPosition).toHaveBeenCalledTimes(1);
  });

  it('pageshow on a NORMAL load (persisted=false) stays inert — the mount already refreshed', async () => {
    localStorage.setItem('geolocation_enabled', 'true');
    permissionsQuery.mockResolvedValue({
      state: 'granted',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
    getCurrentPosition.mockImplementation(success => success(positionOf(43.6, 1.44)));
    renderHook(() => useGeolocation());
    await settle();
    localStorage.removeItem('geolocation_cache');
    getCurrentPosition.mockClear();

    await act(async () => {
      window.dispatchEvent(new Event('pageshow'));
      await new Promise(r => setTimeout(r, 0));
    });

    expect(getCurrentPosition).not.toHaveBeenCalled();
  });
});

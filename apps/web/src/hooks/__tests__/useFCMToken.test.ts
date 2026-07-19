/**
 * useFCMToken — push-notification enrolment.
 *
 * The Firebase helpers are stubbed (they wrap the SDK and the browser
 * Notification API, neither of which exists under jsdom); what is driven here
 * is the hook's own contract:
 *
 *  - the three refusal paths are **distinguishable** — unsupported browser,
 *    Firebase not configured, permission denied — because they call for three
 *    different things to tell the user, and none of them must register a token;
 *  - a refresh failure is deliberately **silent**: the device list is a
 *    convenience, losing it must not raise an error banner over the settings;
 *  - `isLoading` is released on every path, including the failing ones — a
 *    button left spinning is a dead end.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderHook, act, waitFor } from '@/__tests__/test-utils';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: api }));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

const firebase = vi.hoisted(() => ({
  requestNotificationPermission: vi.fn(),
  getNotificationPermission: vi.fn(),
  areNotificationsSupported: vi.fn(),
  isFirebaseConfigured: vi.fn(),
  getDeviceType: vi.fn(),
  isIOSPWA: vi.fn(),
}));
vi.mock('@/lib/firebase', () => firebase);

import { useFCMToken, type RegisteredToken } from '../useFCMToken';

function registered(over: Partial<RegisteredToken> = {}): RegisteredToken {
  return {
    id: 'tok-1',
    device_type: 'web',
    device_name: 'Chrome Browser',
    is_active: true,
    created_at: '2026-07-19T10:00:00Z',
    last_used_at: null,
    ...over,
  };
}

/** Mounts the hook and waits for the mount effect to settle. */
async function setup() {
  const rendered = renderHook(() => useFCMToken());
  await act(async () => {});
  return rendered;
}

beforeEach(() => {
  vi.clearAllMocks();
  firebase.areNotificationsSupported.mockReturnValue(true);
  firebase.isFirebaseConfigured.mockReturnValue(true);
  firebase.isIOSPWA.mockReturnValue(false);
  firebase.getNotificationPermission.mockReturnValue('default');
  firebase.getDeviceType.mockReturnValue('web');
  firebase.requestNotificationPermission.mockResolvedValue('fcm-token-abc');
  api.get.mockResolvedValue({ tokens: [registered()] });
  api.post.mockResolvedValue(undefined);
  api.delete.mockResolvedValue(undefined);
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useFCMToken — initial status', () => {
  it('reports the browser permission when everything is available', async () => {
    firebase.getNotificationPermission.mockReturnValue('default');
    const { result } = await setup();

    expect(result.current.permissionStatus).toBe('default');
    expect(result.current.isLoading).toBe(false);
  });

  it('reports an unsupported browser', async () => {
    firebase.areNotificationsSupported.mockReturnValue(false);
    const { result } = await setup();

    expect(result.current.permissionStatus).toBe('unsupported');
  });

  it('reports a missing Firebase configuration', async () => {
    firebase.isFirebaseConfigured.mockReturnValue(false);
    const { result } = await setup();

    // Distinct from "unsupported": the browser can, the app was not set up.
    expect(result.current.permissionStatus).toBe('not-configured');
  });

  it('loads the registered devices once permission is already granted', async () => {
    firebase.getNotificationPermission.mockReturnValue('granted');
    const { result } = await setup();

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/notifications/tokens'));
    expect(result.current.registeredTokens).toHaveLength(1);
  });

  it('asks for nothing while permission is still default', async () => {
    const { result } = await setup();

    expect(api.get).not.toHaveBeenCalled();
    expect(result.current.registeredTokens).toEqual([]);
  });
});

describe('useFCMToken — enrolling', () => {
  it('registers the token with the device it came from', async () => {
    firebase.getNotificationPermission.mockReturnValueOnce('default').mockReturnValue('granted');
    firebase.getDeviceType.mockReturnValue('android');
    const { result } = await setup();

    let token: string | null = null;
    await act(async () => {
      token = await result.current.requestPermission();
    });

    expect(token).toBe('fcm-token-abc');
    expect(api.post).toHaveBeenCalledWith(
      '/notifications/register-token',
      expect.objectContaining({ token: 'fcm-token-abc', device_type: 'android' })
    );
    expect(result.current.token).toBe('fcm-token-abc');
    expect(result.current.permissionStatus).toBe('granted');
    expect(result.current.isLoading).toBe(false);
  });

  it('refreshes the device list right after enrolling', async () => {
    firebase.getNotificationPermission.mockReturnValueOnce('default').mockReturnValue('granted');
    const { result } = await setup();

    await act(async () => {
      await result.current.requestPermission();
    });

    expect(api.get).toHaveBeenCalledWith('/notifications/tokens');
  });

  it('registers nothing when the user refuses', async () => {
    firebase.requestNotificationPermission.mockResolvedValue(null);
    firebase.getNotificationPermission.mockReturnValueOnce('default').mockReturnValue('denied');
    const { result } = await setup();

    let token: string | null = 'x';
    await act(async () => {
      token = await result.current.requestPermission();
    });

    expect(token).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
    expect(result.current.permissionStatus).toBe('denied');
    expect(result.current.error).toBeNull();
  });

  it.each([
    ['an unsupported browser', 'areNotificationsSupported' as const, /not supported/],
    ['a missing configuration', 'isFirebaseConfigured' as const, /not configured/],
  ])('explains %s without touching Firebase', async (_label, flag, message) => {
    firebase[flag].mockReturnValue(false);
    const { result } = await setup();

    let token: string | null = 'x';
    await act(async () => {
      token = await result.current.requestPermission();
    });

    expect(token).toBeNull();
    expect(firebase.requestNotificationPermission).not.toHaveBeenCalled();
    expect(result.current.error).toMatch(message);
  });

  it('surfaces a failed registration and stops spinning', async () => {
    firebase.getNotificationPermission.mockReturnValueOnce('default').mockReturnValue('granted');
    api.post.mockRejectedValue(new Error('backend refused the token'));
    const { result } = await setup();

    let token: string | null = 'x';
    await act(async () => {
      token = await result.current.requestPermission();
    });

    expect(token).toBeNull();
    expect(result.current.error).toBe('backend refused the token');
    // A button left spinning is a dead end for the user.
    expect(result.current.isLoading).toBe(false);
  });
});

describe('useFCMToken — device list', () => {
  it('stays silent when the list cannot be fetched', async () => {
    firebase.getNotificationPermission.mockReturnValue('granted');
    api.get.mockRejectedValue(new Error('offline'));
    const { result } = await setup();

    await waitFor(() => expect(api.get).toHaveBeenCalled());
    // Losing the device list is not worth an error banner over the settings.
    expect(result.current.error).toBeNull();
    expect(result.current.registeredTokens).toEqual([]);
  });

  it('tolerates a payload without a token array', async () => {
    firebase.getNotificationPermission.mockReturnValue('granted');
    api.get.mockResolvedValue({});
    const { result } = await setup();

    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(result.current.registeredTokens).toEqual([]);
  });

  it('re-syncs the permission status when the list is refreshed', async () => {
    const { result } = await setup();
    firebase.getNotificationPermission.mockReturnValue('granted');

    await act(async () => {
      await result.current.refreshTokens();
    });

    // Another component instance may have been granted permission meanwhile.
    expect(result.current.permissionStatus).toBe('granted');
  });
});

describe('useFCMToken — removing a device', () => {
  it('deletes the device and refreshes the list', async () => {
    firebase.getNotificationPermission.mockReturnValue('granted');
    const { result } = await setup();
    await waitFor(() => expect(result.current.registeredTokens).toHaveLength(1));
    api.get.mockClear();

    await act(async () => {
      await result.current.unregisterToken('tok-1');
    });

    expect(api.delete).toHaveBeenCalledWith('/notifications/tokens/tok-1');
    expect(api.get).toHaveBeenCalledWith('/notifications/tokens');
    expect(result.current.isLoading).toBe(false);
  });

  it('surfaces a failed removal, re-throws it, and stops spinning', async () => {
    firebase.getNotificationPermission.mockReturnValue('granted');
    api.delete.mockRejectedValue(new Error('device is pinned'));
    const { result } = await setup();

    // Deliberate asymmetry with `requestPermission`, which swallows and returns
    // null: a failed removal is re-thrown so the caller can keep the row.
    await act(async () => {
      await expect(result.current.unregisterToken('tok-1')).rejects.toThrow('device is pinned');
    });

    expect(result.current.error).toBe('device is pinned');
    expect(result.current.isLoading).toBe(false);
  });
});

describe('useFCMToken — platform hints', () => {
  it('flags an iOS home-screen install, which needs its own instructions', async () => {
    firebase.isIOSPWA.mockReturnValue(true);
    const { result } = await setup();

    expect(result.current.isIOSPWA).toBe(true);
  });
});

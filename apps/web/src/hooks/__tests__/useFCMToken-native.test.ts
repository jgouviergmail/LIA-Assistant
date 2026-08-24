/**
 * useFCMToken inside a native shell.
 *
 * The shells have neither `Notification` nor `PushManager` (measured on both
 * engines), so every browser check in this hook answers "unsupported" for
 * them — which is the honest answer for a WebView and the wrong one for a
 * shell, whose host CAN receive notifications. The first thing pinned here is
 * that the feature is offered at all.
 *
 * The second is that only ACQUISITION differs. Registering with this server,
 * the device type recorded, the state, the refreshed list: all of it stays the
 * one implementation. A second hook for native would be two paths to keep in
 * step, and the settings screen would have to choose between them.
 *
 * The third is that the browser path is untouched, asserted directly rather
 * than by its absence from this file.
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

const { isNativeShell } = vi.hoisted(() => ({ isNativeShell: vi.fn() }));
vi.mock('@/lib/native/shell', () => ({ isNativeShell }));

const { enrolNativePush } = vi.hoisted(() => ({ enrolNativePush: vi.fn() }));
vi.mock('@/lib/native/push', () => ({ enrolNativePush }));

import { useFCMToken, type EnrollmentResult } from '../useFCMToken';

beforeEach(() => {
  vi.clearAllMocks();
  // A WebView, faithfully: no Notification, no service worker, no web config.
  firebase.areNotificationsSupported.mockReturnValue(false);
  firebase.isFirebaseConfigured.mockReturnValue(false);
  firebase.getNotificationPermission.mockReturnValue('unsupported');
  firebase.isIOSPWA.mockReturnValue(false);
  isNativeShell.mockReturnValue(true);
  api.get.mockResolvedValue({ tokens: [] });
  api.post.mockResolvedValue(undefined);
});

async function enrol(): Promise<EnrollmentResult> {
  const { result } = renderHook(() => useFCMToken());
  let outcome!: EnrollmentResult;
  await act(async () => {
    outcome = await result.current.requestPermission();
  });
  return outcome;
}

describe('the feature is offered at all', () => {
  it('a shell is supported even though its WebView is not', async () => {
    const { result } = renderHook(() => useFCMToken());

    await waitFor(() => expect(result.current.isSupported).toBe(true));
    // Without this the settings screen shows "not supported on this device" on
    // the two platforms that just gained support.
    expect(result.current.isConfigured).toBe(true);
  });

  it('a browser with nothing available is still reported unsupported', async () => {
    isNativeShell.mockReturnValue(false);

    const { result } = renderHook(() => useFCMToken());

    await waitFor(() => expect(result.current.isSupported).toBe(false));
  });

  it('the permission state starts undecided rather than unsupported', async () => {
    const { result } = renderHook(() => useFCMToken());

    // There is no `Notification.permission` to read in a shell: asking the
    // host is the only way to learn it, so nothing is claimed before then.
    await waitFor(() => expect(result.current.permissionStatus).toBe('default'));
  });
});

describe('enrolment through the shell', () => {
  it('registers the shell token with the device type the shell reported', async () => {
    enrolNativePush.mockResolvedValue({ token: 'relay:handle-1', deviceType: 'ios' });

    const outcome = await enrol();

    expect(api.post).toHaveBeenCalledWith(
      '/notifications/register-token',
      expect.objectContaining({ token: 'relay:handle-1', device_type: 'ios' })
    );
    expect(outcome).toEqual({ status: 'enrolled', token: 'relay:handle-1' });
  });

  it('never asks the browser for a token', async () => {
    enrolNativePush.mockResolvedValue({ token: 'fcm-token', deviceType: 'android' });

    await enrol();

    // Calling it would throw in a WebView, where `Notification` is absent.
    expect(firebase.requestNotificationPermission).not.toHaveBeenCalled();
  });

  it('trusts the shell over the user agent for the device type', async () => {
    firebase.getDeviceType.mockReturnValue('web');
    enrolNativePush.mockResolvedValue({ token: 'fcm-token', deviceType: 'android' });

    await enrol();

    // A WebView's user agent is a poor witness of what it is running in; the
    // shell knows for certain.
    expect(api.post).toHaveBeenCalledWith(
      '/notifications/register-token',
      expect.objectContaining({ device_type: 'android' })
    );
  });

  it('reports the permission as granted once a token exists', async () => {
    enrolNativePush.mockResolvedValue({ token: 'fcm-token', deviceType: 'android' });

    const { result } = renderHook(() => useFCMToken());
    await act(async () => {
      await result.current.requestPermission();
    });

    expect(result.current.permissionStatus).toBe('granted');
  });
});

describe('the two ways it can produce nothing', () => {
  it('a refusal is a refusal', async () => {
    enrolNativePush.mockResolvedValue({
      token: null,
      deviceType: 'android',
      reason: 'permission_denied',
    });

    const outcome = await enrol();

    expect(outcome).toEqual({ status: 'denied' });
    expect(api.post).not.toHaveBeenCalled();
  });

  it('a server with no push configured is a failure, not a refusal', async () => {
    enrolNativePush.mockResolvedValue({
      token: null,
      deviceType: 'ios',
      reason: 'not_configured',
    });

    const outcome = await enrol();

    // Telling the user they denied a permission they were never asked for
    // sends them into Settings to fix something that is not broken there.
    expect(outcome).toEqual({ status: 'failed', error: 'not_configured' });
  });

  it('a relay that could not be reached is a failure too', async () => {
    enrolNativePush.mockResolvedValue({
      token: null,
      deviceType: 'ios',
      reason: 'relay_unreachable',
    });

    expect(await enrol()).toEqual({ status: 'failed', error: 'relay_unreachable' });
  });

  it('releases the busy state on every one of them', async () => {
    enrolNativePush.mockResolvedValue({ token: null, deviceType: 'ios', reason: 'not_configured' });

    const { result } = renderHook(() => useFCMToken());
    await act(async () => {
      await result.current.requestPermission();
    });

    expect(result.current.isLoading).toBe(false);
  });
});

describe('the browser path is untouched', () => {
  it('still asks Firebase when there is no shell', async () => {
    isNativeShell.mockReturnValue(false);
    firebase.areNotificationsSupported.mockReturnValue(true);
    firebase.isFirebaseConfigured.mockReturnValue(true);
    firebase.getNotificationPermission.mockReturnValue('granted');
    firebase.getDeviceType.mockReturnValue('web');
    firebase.requestNotificationPermission.mockResolvedValue('web-token');
    enrolNativePush.mockResolvedValue(null);

    const outcome = await enrol();

    expect(firebase.requestNotificationPermission).toHaveBeenCalled();
    expect(api.post).toHaveBeenCalledWith(
      '/notifications/register-token',
      expect.objectContaining({ token: 'web-token', device_type: 'web' })
    );
    expect(outcome).toEqual({ status: 'enrolled', token: 'web-token' });
  });

  it('still reports a browser refusal as denied', async () => {
    isNativeShell.mockReturnValue(false);
    firebase.areNotificationsSupported.mockReturnValue(true);
    firebase.isFirebaseConfigured.mockReturnValue(true);
    firebase.getNotificationPermission.mockReturnValue('denied');
    firebase.requestNotificationPermission.mockResolvedValue(null);
    enrolNativePush.mockResolvedValue(null);

    expect(await enrol()).toEqual({ status: 'denied' });
  });
});

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

const { get, post, remove, useAuth, acquire } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  remove: vi.fn(),
  useAuth: vi.fn(),
  acquire: vi.fn(),
}));
const { toast } = vi.hoisted(() => ({ toast: { error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', () => ({ default: { get, post, delete: remove } }));
vi.mock('@/lib/firebase', () => ({
  requestNotificationPermission: acquire,
  getNotificationPermission: () => 'granted',
  areNotificationsSupported: () => true,
  isFirebaseConfigured: () => true,
  getDeviceType: () => 'web',
  isIOSPWA: () => false,
}));
vi.mock('@/lib/native/push', () => ({ enrolNativePush: async () => null }));
vi.mock('@/lib/native/shell', () => ({ isNativeShell: () => false }));
import { useFCMToken } from '../useFCMToken';
import { publishApplicationResources } from '@/lib/application-resources';

beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue({ tokens: [] });
});

it('discards an old-account notification-device response', async () => {
  let finish: (value: { tokens: object[] }) => void = () => {};
  get.mockImplementationOnce(
    () =>
      new Promise(done => {
        finish = done;
      })
  );
  const { result, rerender } = renderHook(() => useFCMToken());
  await waitFor(() => expect(get).toHaveBeenCalled());
  useAuth.mockReturnValue({ user: { id: 'two' } });
  rerender();
  await act(async () => {
    finish({ tokens: [{ id: 'private-device', device_name: 'Previous account' }] });
  });
  expect(result.current.registeredTokens).toEqual([]);
});

it('does not register a push credential acquired for a previous account', async () => {
  let finish: (value: string) => void = () => {};
  acquire.mockImplementationOnce(
    () =>
      new Promise(done => {
        finish = done;
      })
  );
  const { result, rerender } = renderHook(() => useFCMToken());
  let pending: ReturnType<typeof result.current.requestPermission>;
  act(() => {
    pending = result.current.requestPermission();
  });
  await waitFor(() => expect(acquire).toHaveBeenCalled());
  useAuth.mockReturnValue({ user: { id: 'two' } });
  rerender();
  await act(async () => {
    finish('private-acquired-token');
    await pending;
  });
  expect(post).not.toHaveBeenCalled();
  expect(result.current.token).toBeNull();
});

it('rejects an old deletion callback after A-to-B-to-A without issuing HTTP', async () => {
  const { result, rerender } = renderHook(() => useFCMToken());
  const stale = result.current.unregisterToken;
  useAuth.mockReturnValue({ user: { id: 'two' } });
  rerender();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  rerender();
  await act(async () => {
    await stale('old-device');
  });
  expect(remove).not.toHaveBeenCalled();
});

it('rereads owned notification registrations after an assistant removal', async () => {
  get.mockResolvedValueOnce({ tokens: [{ id: 'removed-device' }] });
  const { result } = renderHook(() => useFCMToken());
  await waitFor(() => expect(result.current.registeredTokens).toHaveLength(1));
  act(() => publishApplicationResources('one', new Set(['notification_devices'])));
  await waitFor(() => expect(result.current.registeredTokens).toEqual([]));
});

it('never resurrects a removed registration from an older overlapping refresh', async () => {
  const { result } = renderHook(() => useFCMToken());
  await act(async () => {});
  let finish: (value: { tokens: object[] }) => void = () => {};
  get.mockImplementationOnce(
    () =>
      new Promise(done => {
        finish = done;
      })
  );
  let oldRead: Promise<void>;
  act(() => {
    oldRead = result.current.refreshTokens();
  });
  await act(async () => {
    await result.current.refreshTokens();
  });
  await act(async () => {
    finish({ tokens: [{ id: 'removed-device' }] });
    await oldRead;
  });
  expect(result.current.registeredTokens).toEqual([]);
});

it('does not report a false sync failure when a newer canonical read has succeeded', async () => {
  const { result } = renderHook(() => useFCMToken());
  await act(async () => {});
  let finish: (value: { tokens: object[] }) => void = () => {};
  get.mockImplementationOnce(
    () =>
      new Promise(done => {
        finish = done;
      })
  );
  act(() => publishApplicationResources('one', new Set(['notification_devices'])));
  await act(async () => {
    await result.current.refreshTokens();
  });
  await act(async () => {
    finish({ tokens: [{ id: 'removed-device' }] });
  });
  expect(result.current.registeredTokens).toEqual([]);
  expect(toast.error).not.toHaveBeenCalled();
});

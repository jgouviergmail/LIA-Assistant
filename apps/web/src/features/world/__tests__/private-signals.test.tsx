import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { makeUser } from '@/__tests__/factories';
import type { UseNotificationsOptions } from '@/hooks/useNotifications';
import { publishApplicationResources } from '@/lib/application-resources';
import { useWorldPrivateSignals } from '../useWorldPrivateSignals';

const owner = 'ef910df4-a74c-4007-a41c-88dc9a43655d';
const id = '51bb9a96-5f4f-431e-9887-a5922ac6fa8a';
const state = vi.hoisted(() => ({
  user: undefined as ReturnType<typeof makeUser> | undefined,
  options: {} as UseNotificationsOptions,
  get: vi.fn(),
  features: { sms_enabled: true, workboard_enabled: true, attachments_enabled: true },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: state.user }) }));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({ config: { features: state.features } }),
}));
vi.mock('@/hooks/useNotifications', () => ({
  useNotifications: (options: UseNotificationsOptions) => {
    state.options = options;
    return { isConnected: true };
  },
}));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get: state.get },
}));
vi.mock('@/lib/logger', () => ({ logger: { error: vi.fn() } }));
beforeEach(() => {
  state.user = makeUser({ id: owner, is_active: true });
  state.features = { sms_enabled: true, workboard_enabled: true, attachments_enabled: true };
  state.get
    .mockReset()
    .mockImplementation(async (path: string) =>
      path.includes('needs-me') ? { total: 2, tickets: [{ id }] } : { total: 1, items: [{ id }] }
    );
});
it('uses native read aggregates and resource invalidation without polling assets or creating model work', async () => {
  const { result } = renderHook(() => useWorldPrivateSignals(owner, true));
  await waitFor(() =>
    expect(result.current.signals.some(item => item.kind === 'workboard')).toBe(true)
  );
  expect(state.get.mock.calls.map(call => call[0])).toEqual(['/workboard/needs-me']);
  act(() => publishApplicationResources('other', new Set(['generated_assets'])));
  expect(state.get).toHaveBeenCalledTimes(1);
  act(() => publishApplicationResources(owner, new Set(['generated_assets'])));
  await waitFor(() =>
    expect(
      result.current.signals.filter(item =>
        ['images', 'documents', 'screenshots'].includes(item.kind)
      )
    ).toHaveLength(3)
  );
  expect(state.get).toHaveBeenCalledTimes(4);
  expect(state.get.mock.calls.slice(1).map(call => call[0])).toEqual(
    expect.arrayContaining([
      '/generated-assets?family=images&limit=1',
      '/generated-assets?family=documents&limit=1',
      '/generated-assets?family=screenshots&limit=1',
    ])
  );
  const image = result.current.signals.find(item => item.kind === 'images');
  if (!image) throw new Error('Missing authenticated image count');
  act(() => result.current.acknowledge(image.propId));
  expect(result.current.signals.some(item => item.kind === 'images')).toBe(false);
  expect(result.current.signals.some(item => item.kind === 'documents')).toBe(true);
  const next = Promise.withResolvers<unknown>();
  state.get.mockReturnValue(next.promise);
  act(() => publishApplicationResources(owner, new Set(['generated_assets'])));
  expect(result.current.signals.some(item => item.kind === 'images')).toBe(false);
  await act(async () => next.resolve({ total: 3, items: [{ id }] }));
  await waitFor(() =>
    expect(result.current.signals.find(item => item.kind === 'images')?.count).toBe(3)
  );
});
it('shares phone acknowledgment and hides withdrawn SMS and obsolete owners immediately', async () => {
  const { result, rerender, unmount } = renderHook(
    ({ enabled }) => useWorldPrivateSignals(owner, enabled),
    { initialProps: { enabled: true } }
  );
  await waitFor(() => expect(state.get).toHaveBeenCalledOnce());
  const signal = {
    type: 'sms_received' as const,
    user_id: owner,
    message_id: id,
    occurrence_id: owner,
  };
  act(() => state.options.onSmsReceived?.(signal));
  expect(result.current.signals.some(item => item.kind === 'sms')).toBe(true);
  const notice = result.current.entries[0];
  act(() => result.current.read(notice.key));
  expect(result.current.signals.some(item => item.kind === 'sms')).toBe(false);
  act(() => state.options.onSmsReceived?.({ ...signal, occurrence_id: id }));
  const old = state.options.onSmsReceived;
  state.features.sms_enabled = false;
  rerender({ enabled: true });
  expect(result.current.entries.some(item => item.kind === 'sms')).toBe(false);
  rerender({ enabled: false });
  act(() => old?.({ ...signal, occurrence_id: id }));
  expect(result.current.signals).toEqual([]);
  unmount();
  const count = state.get.mock.calls.length;
  act(() => state.options.onReconnected?.());
  expect(state.get).toHaveBeenCalledTimes(count);
});
it('marks a reconnect gap as uncertainty and failed native reads as unavailable, never zero', async () => {
  state.get.mockRejectedValue(new Error('offline'));
  const { result } = renderHook(() => useWorldPrivateSignals(owner, true));
  await waitFor(() =>
    expect(result.current.signals.find(item => item.kind === 'workboard')?.status).toBe(
      'unavailable'
    )
  );
  expect(result.current.signals.find(item => item.kind === 'workboard')?.count).toBeNull();
  const reads = state.get.mock.calls.length;
  act(() => state.options.onReconnected?.());
  expect(result.current.remindersUncertain).toBe(true);
  expect(result.current.entries).toEqual([]);
  // The gap re-reads every durable aggregate; a re-read that fails still reads unavailable.
  await waitFor(() =>
    expect(
      result.current.signals
        .filter(item => ['images', 'documents', 'screenshots'].includes(item.kind))
        .map(item => [item.status, item.count])
    ).toEqual([
      ['unavailable', null],
      ['unavailable', null],
      ['unavailable', null],
    ])
  );
  expect(state.get).toHaveBeenCalledTimes(reads + 4);
  expect(result.current.signals.find(item => item.kind === 'workboard')).toMatchObject({
    status: 'unavailable',
    count: null,
  });
});
it('revokes old SMS callbacks and readers across permission withdrawal without disabling the World', async () => {
  const { result, rerender } = renderHook(() => useWorldPrivateSignals(owner, true));
  await waitFor(() => expect(state.get).toHaveBeenCalledOnce());
  const oldDelivery = state.options.onSmsReceived;
  const oldRead = result.current.read;
  state.features.sms_enabled = false;
  rerender();
  act(() =>
    oldDelivery?.({ type: 'sms_received', user_id: owner, message_id: id, occurrence_id: id })
  );
  act(() => {
    expect(oldRead('sms:' + id)).toBeNull();
  });
  act(() =>
    state.options.onNotification?.({
      id: 'reminder',
      type: 'reminder',
      reminder_id: 'reminder',
      content: 'Still received',
      timestamp: new Date(),
      read: false,
    })
  );
  expect(result.current.entries.map(item => item.kind)).toEqual(['reminder']);
  state.features.sms_enabled = true;
  rerender();
  expect(result.current.entries.map(item => item.kind)).toEqual(['reminder']);
  act(() =>
    oldDelivery?.({ type: 'sms_received', user_id: owner, message_id: id, occurrence_id: owner })
  );
  expect(result.current.entries.map(item => item.kind)).toEqual(['reminder']);
  act(() =>
    state.options.onSmsReceived?.({
      type: 'sms_received',
      user_id: owner,
      message_id: id,
      occurrence_id: owner,
    })
  );
  expect(result.current.entries.map(item => item.kind)).toEqual(['sms', 'reminder']);
});
it('keeps a marker through its re-read and withdraws it only when that read fails', async () => {
  const { result } = renderHook(() => useWorldPrivateSignals(owner, true));
  const board = () => result.current.signals.find(item => item.kind === 'workboard');
  await waitFor(() => expect(board()?.count).toBe(2));
  const reread = Promise.withResolvers<unknown>();
  state.get.mockReturnValueOnce(reread.promise);
  act(() => publishApplicationResources(owner, new Set(['workboard'])));
  // Refresh in place: the answer on screen stays until its successor lands.
  expect(board()).toMatchObject({ status: 'ready', count: 2 });
  await act(async () => reread.reject(new Error('offline')));
  await waitFor(() => expect(board()?.status).toBe('unavailable'));
  const retry = Promise.withResolvers<unknown>();
  state.get.mockReturnValueOnce(retry.promise);
  act(() => publishApplicationResources(owner, new Set(['workboard'])));
  // A retry never resurrects the answer that the failed read withdrew.
  expect(board()).toMatchObject({ status: 'unavailable', count: null });
  await act(async () => retry.resolve({ total: 5, tickets: [{ id }] }));
  await waitFor(() => expect(board()).toMatchObject({ status: 'ready', count: 5 }));
});
it('never lets a previous owner callback populate the next owner entries', async () => {
  const next = '7a3c1f90-2b4d-4e6f-8a1b-3c5d7e9f0a2b';
  const { result, rerender } = renderHook(({ id }) => useWorldPrivateSignals(id, true), {
    initialProps: { id: owner },
  });
  await waitFor(() => expect(state.get).toHaveBeenCalled());
  const oldSms = state.options.onSmsReceived;
  const oldNotice = state.options.onNotification;
  const oldReconnected = state.options.onReconnected;
  state.user = makeUser({ id: next, is_active: true });
  rerender({ id: next });
  act(() => {
    oldSms?.({ type: 'sms_received', user_id: owner, message_id: id, occurrence_id: id });
    oldNotice?.({
      id: 'reminder',
      type: 'reminder',
      reminder_id: 'reminder',
      content: 'Belongs to the previous owner',
      timestamp: new Date(),
      read: false,
    });
    oldReconnected?.();
  });
  expect(result.current.entries).toEqual([]);
  expect(result.current.remindersUncertain).toBe(false);
  expect(result.current.signals.some(item => item.kind === 'sms' || item.kind === 'reminder')).toBe(
    false
  );
  // The next owner's own read lands for the next owner alone.
  await waitFor(() =>
    expect(result.current.signals.find(item => item.kind === 'workboard')?.count).toBe(2)
  );
  expect(result.current.entries).toEqual([]);
});

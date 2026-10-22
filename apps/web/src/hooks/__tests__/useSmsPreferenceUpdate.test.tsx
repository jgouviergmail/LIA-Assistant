import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const { get, patch, useAuth } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get, patch },
}));
vi.mock('@/lib/logger', () => ({ logger: { error: vi.fn() } }));
import { useSmsPreferenceUpdate } from '../useSmsPreferenceUpdate';
import { useApplicationAccountQuery } from '../useApplicationAccountQuery';
import type { SmsSettings } from '@/types/sms';

const preferences = { ingestion_enabled: true, assistant_enabled: false, push_enabled: true };
const settings: SmsSettings = {
  preferences,
  usage: {
    message_count: 0,
    receipt_count: 0,
    logical_bytes: 0,
    max_logical_bytes: 100,
    max_receipts: 100,
    last_received_at: null,
  },
  device_deliveries: { pending: 0, sending: 0, sent: 0, failed: 0, unknown: 0, cancelled: 0 },
};
beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue(settings);
  useAuth.mockReturnValue({ user: { id: 'owner' } });
});
function useControls() {
  const query = useApplicationAccountQuery<SmsSettings>('/sms/settings', 'testSmsPreference');
  return { query, update: useSmsPreferenceUpdate(query) };
}

it('sends one write during a pending click and keeps the other fields', async () => {
  let finish: ((value: typeof preferences) => void) | undefined;
  patch.mockImplementationOnce(
    () =>
      new Promise<typeof preferences>(resolve => {
        finish = resolve;
      })
  );
  const { result } = renderHook(useControls);
  await waitFor(() => expect(result.current.query.data).toEqual(settings));
  let pending: Promise<void> | undefined;
  act(() => {
    pending = result.current.update.updatePreference('assistant_enabled', true);
  });
  await act(async () => {
    await result.current.update.updatePreference('push_enabled', false);
  });
  expect(patch).toHaveBeenCalledTimes(1);
  expect(result.current.update.saving).toBe(true);
  await act(async () => {
    finish?.({ ...preferences, assistant_enabled: true });
    await pending;
  });
  expect(result.current.query.data?.preferences).toEqual({
    ...preferences,
    assistant_enabled: true,
  });
  expect(result.current.update.saving).toBe(false);
});

it('discards a late response across account lifetimes, including return to the original account', async () => {
  let finish: ((value: typeof preferences) => void) | undefined;
  patch.mockImplementationOnce(
    () =>
      new Promise<typeof preferences>(resolve => {
        finish = resolve;
      })
  );
  const { result, rerender } = renderHook(useControls);
  await waitFor(() => expect(result.current.query.data).toEqual(settings));
  let pending: Promise<void> | undefined;
  act(() => {
    pending = result.current.update.updatePreference('assistant_enabled', true);
  });
  useAuth.mockReturnValue({ user: { id: 'other' } });
  rerender();
  await waitFor(() => expect(result.current.query.data).toEqual(settings));
  await act(async () => {
    finish?.({ ...preferences, assistant_enabled: true });
    await pending;
  });
  expect(result.current.query.data?.preferences.assistant_enabled).toBe(false);
  useAuth.mockReturnValue({ user: { id: 'owner' } });
  rerender();
  await waitFor(() => expect(result.current.query.data).toEqual(settings));
  expect(result.current.update.saving).toBe(false);
});

it('rejects an invalid acknowledgement without publishing invented preference values', async () => {
  patch.mockResolvedValue({ assistant_enabled: 'yes' });
  const { result } = renderHook(useControls);
  await waitFor(() => expect(result.current.query.data).toEqual(settings));
  await act(async () => {
    await result.current.update.updatePreference('assistant_enabled', true);
  });
  expect(result.current.update.error).toBe(true);
  expect(result.current.query.data).toEqual(settings);
});

it('prevents an earlier metadata refresh from overwriting the acknowledged change', async () => {
  const { result } = renderHook(useControls);
  await waitFor(() => expect(result.current.query.data).toEqual(settings));
  let finishRead: ((value: SmsSettings) => void) | undefined;
  get.mockImplementationOnce(
    () =>
      new Promise<SmsSettings>(resolve => {
        finishRead = resolve;
      })
  );
  let reading: Promise<boolean> | undefined;
  act(() => {
    reading = result.current.query.refetchVerified();
  });
  patch.mockResolvedValue({ ...preferences, assistant_enabled: true });
  await act(async () => {
    await result.current.update.updatePreference('assistant_enabled', true);
  });
  await act(async () => {
    finishRead?.(settings);
    expect(await reading).toBe(false);
  });
  expect(result.current.query.data?.preferences.assistant_enabled).toBe(true);
});

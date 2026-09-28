/**
 * The radio's settings save in order: one full replace in flight, the latest
 * state after it — and a failure goes back to what the server accepted.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api-client';
import { RADIO_ENDPOINTS } from '@/lib/radio/api';
import { radioOptions, radioPreferences } from '@/lib/radio/__tests__/fixtures';
import type { RadioWrite } from '@/lib/radio/errors';
import type { RadioPreferences } from '@/lib/radio/types';
import { bumpRevision } from '@/stores/revisionStore';
import { useRadioSettings } from '../useRadioSettings';

const mockApi = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client');
  return { ...actual, default: mockApi, apiClient: mockApi };
});

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

afterEach(() => vi.clearAllMocks());

const STORED: RadioPreferences = radioPreferences();

function serve(): void {
  mockApi.get.mockImplementation(async (endpoint: string) =>
    endpoint === RADIO_ENDPOINTS.options ? radioOptions() : STORED
  );
}

function deferred(error: Error = new Error('refused')): {
  promise: Promise<RadioPreferences>;
  resolve: () => void;
  reject: () => void;
} {
  let resolve = (): void => undefined;
  let reject = (): void => undefined;
  const promise = new Promise<RadioPreferences>((ok, ko) => {
    resolve = () => ok(STORED);
    reject = () => ko(error);
  });
  return { promise, resolve, reject };
}

const PENDING: Promise<RadioWrite<RadioPreferences>> = Promise.resolve({
  ok: false,
  refusal: null,
});

describe('useRadioSettings — saves', () => {
  it('sends a change made during a save after it, the latest state only', async () => {
    serve();
    const first = deferred();
    mockApi.put.mockReturnValueOnce(first.promise).mockResolvedValue(STORED);
    const { result } = renderHook(() => useRadioSettings());
    await waitFor(() => expect(result.current.preferences).not.toBeNull());

    const a = { ...STORED, public_mode: true };
    const b = { ...a, timer_minutes: 45 };
    const c = { ...b, verification: 'all' as const };
    let saving = PENDING;
    act(() => {
      saving = result.current.save(a);
    });
    await act(async () => {
      await result.current.save(b);
    });
    await act(async () => {
      await result.current.save(c);
    });
    expect(result.current.preferences).toEqual(c); // shown at once
    expect(mockApi.put).toHaveBeenCalledTimes(1); // one replace in flight

    await act(async () => {
      first.resolve();
      expect(await saving).toEqual({ ok: true, value: a });
    });
    expect(mockApi.put.mock.calls.map(call => call[1])).toEqual([a, c]); // b coalesced away
  });

  it('goes back to what the server accepted when a save fails', async () => {
    serve();
    const refused = deferred();
    mockApi.put.mockReturnValueOnce(refused.promise);
    const { result } = renderHook(() => useRadioSettings());
    await waitFor(() => expect(result.current.preferences).not.toBeNull());

    let saving = PENDING;
    act(() => {
      saving = result.current.save({ ...STORED, public_mode: true });
    });
    expect(result.current.preferences?.public_mode).toBe(true);
    await act(async () => {
      refused.reject();
      expect(await saving).toEqual({ ok: false, refusal: null });
    });
    expect(result.current.preferences).toEqual(STORED);
  });

  it('says why when the API named its refusal, quoting the bound it published', async () => {
    serve();
    const refused = deferred(
      new ApiError('refused', 422, { detail: { code: 'radio_timer_too_long', max_minutes: 240 } })
    );
    mockApi.put.mockReturnValueOnce(refused.promise);
    const { result } = renderHook(() => useRadioSettings());
    await waitFor(() => expect(result.current.preferences).not.toBeNull());

    let saving = PENDING;
    act(() => {
      saving = result.current.save({ ...STORED, timer_minutes: 999 });
    });
    await act(async () => {
      refused.reject();
      expect(await saving).toEqual({
        ok: false,
        refusal: { key: 'radio.errors.radio_timer_too_long', values: { max: 240 } },
      });
    });
    expect(result.current.preferences).toEqual(STORED);
  });
});

describe('useRadioSettings — the radio engine changed elsewhere', () => {
  it('re-reads the options and the settings when the radio voices change', async () => {
    serve();
    const { result } = renderHook(() => useRadioSettings());
    await waitFor(() => expect(result.current.preferences).not.toBeNull());
    expect(mockApi.get).toHaveBeenCalledTimes(2);

    act(() => bumpRevision('radio_voices'));

    await waitFor(() => expect(mockApi.get).toHaveBeenCalledTimes(4));
    const read = mockApi.get.mock.calls.map(call => call[0]).slice(2);
    expect(read.sort()).toEqual([RADIO_ENDPOINTS.options, RADIO_ENDPOINTS.preferences].sort());
  });

  it('lets a choice saved before the change yield to what the server now reads', async () => {
    serve();
    mockApi.put.mockResolvedValue(STORED);
    const { result } = renderHook(() => useRadioSettings());
    await waitFor(() => expect(result.current.preferences).not.toBeNull());
    const chosen = { ...STORED, voices: { host: 'voice-of-the-old-engine' } };
    await act(async () => {
      await result.current.save(chosen);
    });
    expect(result.current.preferences).toEqual(chosen);

    // The engine changed: the server reads that voice as automatic now.
    act(() => bumpRevision('radio_voices'));

    await waitFor(() => expect(result.current.preferences).toEqual(STORED));
  });
});

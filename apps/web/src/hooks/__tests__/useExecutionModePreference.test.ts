/**
 * useExecutionModePreference — the person's mode (ADR-070, ADR-390): the
 * account says which mode is chosen, the instance says what « auto » does
 * here, and a choice is saved once, then read back from the account.
 *
 * The real `useApiQuery` / `useApiMutation` run; only the transport is faked,
 * so the oracles are the requests that leave and what the hook then reports.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeUser } from '@/__tests__/factories';
import { useExecutionModePreference } from '@/hooks/useExecutionModePreference';
import type { User } from '@/lib/auth';

const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get, patch } }));
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

const ENDPOINT = '/auth/me/execution-mode-preference';
const refreshUser = vi.fn(async () => {});

function signedIn(over: Partial<User> = {}): void {
  useAuth.mockReturnValue({ user: makeUser(over), refreshUser });
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue({ execution_mode: 'pipeline', auto_resolution: 'decided' });
  patch.mockResolvedValue({ execution_mode: 'auto', auto_resolution: 'decided' });
});

describe('useExecutionModePreference', () => {
  it('reads the chosen mode from the account and what « auto » does from the instance', async () => {
    signedIn({ execution_mode: 'auto' });
    get.mockResolvedValue({ execution_mode: 'auto', auto_resolution: 'always_react' });

    const { result } = renderHook(() => useExecutionModePreference());

    expect(result.current.mode).toBe('auto');
    await waitFor(() => expect(result.current.autoResolution).toBe('always_react'));
    expect(get).toHaveBeenCalledWith(ENDPOINT, expect.anything());
  });

  it('asks nothing before the account is known', async () => {
    useAuth.mockReturnValue({ user: null, refreshUser });

    const { result } = renderHook(() => useExecutionModePreference());

    await act(async () => {});
    expect(get).not.toHaveBeenCalled();
    expect(result.current.autoResolution).toBeNull();
    await act(async () => {
      expect(await result.current.choose('react')).toBe('ignored');
    });
    expect(patch).not.toHaveBeenCalled();
  });

  it('saves a choice, then reads the account back', async () => {
    signedIn({ execution_mode: 'pipeline' });
    patch.mockResolvedValue({ execution_mode: 'auto', auto_resolution: 'always_pipeline' });
    const { result } = renderHook(() => useExecutionModePreference());

    let outcome = '';
    await act(async () => {
      outcome = await result.current.choose('auto');
    });

    expect(outcome).toBe('saved');
    expect(patch).toHaveBeenCalledWith(ENDPOINT, { execution_mode: 'auto' }, undefined);
    expect(refreshUser).toHaveBeenCalledTimes(1);
    // The answer to the save says what « auto » does here, as fresh as a read.
    expect(result.current.autoResolution).toBe('always_pipeline');
    expect(result.current.saving).toBeNull();
  });

  it('leaves the account as it was when the save fails', async () => {
    signedIn({ execution_mode: 'pipeline' });
    patch.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useExecutionModePreference());

    let outcome = '';
    await act(async () => {
      outcome = await result.current.choose('react');
    });

    expect(outcome).toBe('failed');
    expect(refreshUser).not.toHaveBeenCalled();
    expect(result.current.saving).toBeNull();
  });

  it('saves one choice at a time and says which one is on its way', async () => {
    signedIn({ execution_mode: 'pipeline' });
    let release: (value: unknown) => void = () => {};
    patch.mockReturnValue(new Promise(resolve => (release = resolve)));
    const { result } = renderHook(() => useExecutionModePreference());

    let first: Promise<string> = Promise.resolve('');
    act(() => {
      first = result.current.choose('auto');
    });
    await waitFor(() => expect(result.current.saving).toBe('auto'));

    let second = '';
    await act(async () => {
      second = await result.current.choose('react');
    });
    expect(second).toBe('ignored');
    expect(patch).toHaveBeenCalledTimes(1);

    await act(async () => {
      release({ execution_mode: 'auto', auto_resolution: 'decided' });
      expect(await first).toBe('saved');
    });
    expect(result.current.saving).toBeNull();
  });

  it('reads again what « auto » does when the menu asks', async () => {
    signedIn({ execution_mode: 'auto' });
    const { result } = renderHook(() => useExecutionModePreference());
    await waitFor(() => expect(result.current.autoResolution).toBe('decided'));

    // An administrator switched the decision off since the page loaded.
    get.mockResolvedValue({ execution_mode: 'auto', auto_resolution: 'always_react' });
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.autoResolution).toBe('always_react');
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('reads nothing again before the account is known', async () => {
    useAuth.mockReturnValue({ user: null, refreshUser });
    const { result } = renderHook(() => useExecutionModePreference());

    await act(async () => {
      await result.current.refresh();
    });

    expect(get).not.toHaveBeenCalled();
  });

  it('sends nothing for the mode already chosen', async () => {
    signedIn({ execution_mode: 'react' });
    const { result } = renderHook(() => useExecutionModePreference());

    await act(async () => {
      expect(await result.current.choose('react')).toBe('ignored');
    });
    expect(patch).not.toHaveBeenCalled();
  });
});

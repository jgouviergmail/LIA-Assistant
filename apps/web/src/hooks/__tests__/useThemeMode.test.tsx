/**
 * useThemeMode — the single owner of the display-mode state.
 *
 * Covered indirectly through `ThemeToggle`, but the two failure modes below are
 * invisible from there, and both were REAL defects found in cold review:
 *
 *  1. Restoring a stored mode was compared against `resolvedTheme` instead of
 *     the chosen `theme`. A record saying "dark" for a user sitting on `system`
 *     (resolving dark) then never became explicit — Settings kept showing
 *     "System" while the server said "Dark".
 *  2. Nothing serialised the PATCH writes. Three quick presses fired three
 *     concurrent requests to the same endpoint, and HTTP gives no ordering
 *     guarantee, so the server could end up storing a state the user had
 *     already left.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

import { OLED_STORAGE_KEY } from '@/lib/theme-mode';

const { setTheme, themeState } = vi.hoisted(() => ({
  setTheme: vi.fn(),
  themeState: { theme: 'light' as string, resolvedTheme: 'light' as string | undefined },
}));
vi.mock('next-themes', () => ({ useTheme: () => ({ ...themeState, setTheme }) }));

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate }) }));

import { useThemeMode } from '../useThemeMode';

beforeEach(() => {
  vi.clearAllMocks();
  mutate.mockResolvedValue(undefined);
  useAuth.mockReturnValue({ user: { id: 'u1' }, refreshUser: vi.fn() });
  themeState.theme = 'light';
  themeState.resolvedTheme = 'light';
  window.localStorage.clear();
  document.documentElement.removeAttribute('data-oled');
});

describe('useThemeMode — restoring the stored preference', () => {
  it('saves the queued newer choice even when the previous write fails', async () => {
    let reject: ((error: Error) => void) | undefined;
    mutate
      .mockImplementationOnce(
        () =>
          new Promise<void>((_resolve, refuse) => {
            reject = refuse;
          })
      )
      .mockResolvedValue(undefined);
    const { result } = renderHook(() => useThemeMode());
    let first: Promise<void> | undefined;
    act(() => {
      first = result.current.apply({ mode: 'dark', oled: false });
    });
    await act(async () => {
      await result.current.apply({ mode: 'light', oled: false });
    });
    await act(async () => {
      reject?.(new Error('offline'));
      await first;
    });
    expect(mutate).toHaveBeenLastCalledWith('/users/u1', { theme: 'light' });
  });
  it('applies the new account system mode instead of carrying another account local choice', () => {
    useAuth.mockReturnValue({ user: { id: 'u1', theme: 'system' }, refreshUser: vi.fn() });
    const { rerender } = renderHook(() => useThemeMode());
    setTheme.mockClear();
    useAuth.mockReturnValue({ user: { id: 'u2', theme: 'system' }, refreshUser: vi.fn() });
    rerender();
    expect(setTheme).toHaveBeenCalledWith('system');
  });

  it('restores an explicit dark even while system already resolves to dark', async () => {
    // The defect: comparing against `resolvedTheme` made this a no-op, so the
    // Settings radio stayed on "System" while the record said "Dark".
    themeState.theme = 'system';
    themeState.resolvedTheme = 'dark';
    useAuth.mockReturnValue({ user: { id: 'u1', theme: 'dark' }, refreshUser: vi.fn() });

    renderHook(() => useThemeMode());

    await waitFor(() => expect(setTheme).toHaveBeenCalledWith('dark'));
  });

  it('restores an explicit light while system resolves to light', async () => {
    themeState.theme = 'system';
    themeState.resolvedTheme = 'light';
    useAuth.mockReturnValue({ user: { id: 'u1', theme: 'light' }, refreshUser: vi.fn() });

    renderHook(() => useThemeMode());

    await waitFor(() => expect(setTheme).toHaveBeenCalledWith('light'));
  });

  it('does not fight the provider when the mode already matches', async () => {
    themeState.theme = 'dark';
    themeState.resolvedTheme = 'dark';
    useAuth.mockReturnValue({ user: { id: 'u1', theme: 'dark' }, refreshUser: vi.fn() });

    renderHook(() => useThemeMode());

    await waitFor(() => expect(setTheme).not.toHaveBeenCalled());
  });

  it('restores OLED as dark plus the attribute', async () => {
    themeState.theme = 'light';
    themeState.resolvedTheme = 'light';
    useAuth.mockReturnValue({ user: { id: 'u1', theme: 'oled' }, refreshUser: vi.fn() });

    renderHook(() => useThemeMode());

    await waitFor(() => {
      expect(setTheme).toHaveBeenCalledWith('dark');
      expect(document.documentElement.hasAttribute('data-oled')).toBe(true);
      expect(window.localStorage.getItem(OLED_STORAGE_KEY)).toBe('1');
    });
  });

  it('leaves system alone — it is the column default, not a value to override', async () => {
    useAuth.mockReturnValue({ user: { id: 'u1', theme: 'system' }, refreshUser: vi.fn() });
    renderHook(() => useThemeMode());
    await waitFor(() => expect(setTheme).not.toHaveBeenCalled());
  });
});

describe('useThemeMode — persistence under rapid changes', () => {
  it('keeps each queued preference write addressed to the account that chose it', async () => {
    let release: (() => void) | undefined;
    const held = new Promise<void>(resolve => {
      release = resolve;
    });
    mutate.mockImplementationOnce(() => held);
    const { result, rerender } = renderHook(() => useThemeMode());
    let firstSave: Promise<void> | undefined;
    act(() => {
      firstSave = result.current.apply({ mode: 'dark', oled: false });
    });
    useAuth.mockReturnValue({ user: { id: 'u2' }, refreshUser: vi.fn() });
    rerender();
    await act(async () => {
      await result.current.apply({ mode: 'light', oled: false });
    });
    await act(async () => {
      release?.();
      await firstSave;
    });
    expect(mutate.mock.calls).toEqual([
      ['/users/u1', { theme: 'dark' }],
      ['/users/u2', { theme: 'light' }],
    ]);
  });

  it('applies a confirmed change back to system without overriding the initial column default', () => {
    useAuth.mockReturnValue({ user: { id: 'u1', theme: 'dark' }, refreshUser: vi.fn() });
    const { rerender } = renderHook(() => useThemeMode());
    setTheme.mockClear();
    useAuth.mockReturnValue({ user: { id: 'u1', theme: 'system' }, refreshUser: vi.fn() });
    rerender();
    expect(setTheme).toHaveBeenCalledWith('system');
  });
  it('never leaves the server on a state the user has left', async () => {
    // Three presses in a burst. Whatever the request scheduling, the LAST
    // value the user chose must be the last one written.
    let resolvers: Array<() => void> = [];
    mutate.mockImplementation(
      () =>
        new Promise<void>(resolve => {
          resolvers.push(resolve);
        })
    );

    const { result } = renderHook(() => useThemeMode());

    await act(async () => {
      void result.current.apply({ mode: 'dark', oled: false });
      void result.current.apply({ mode: 'dark', oled: true });
      void result.current.apply({ mode: 'light', oled: false });
    });

    // Drain whatever is in flight, in any order.
    await act(async () => {
      while (resolvers.length) {
        const pending = resolvers;
        resolvers = [];
        pending.forEach(r => r());
        await Promise.resolve();
      }
    });

    const written = mutate.mock.calls.map(call => call[1].theme);
    expect(written.at(-1), `writes were: ${JSON.stringify(written)}`).toBe('light');
  });

  it('collapses a burst rather than firing one request per press', async () => {
    const { result } = renderHook(() => useThemeMode());

    await act(async () => {
      await Promise.all([
        result.current.apply({ mode: 'dark', oled: false }),
        result.current.apply({ mode: 'dark', oled: true }),
        result.current.apply({ mode: 'light', oled: false }),
      ]);
    });

    // Three presses must not mean three round-trips; only the endpoints the
    // user actually rested on need to reach the server.
    expect(mutate.mock.calls.length).toBeLessThan(3);
  });

  it('does not persist at all without a signed-in user', async () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    const { result } = renderHook(() => useThemeMode());
    await act(async () => {
      await result.current.apply({ mode: 'dark', oled: false });
    });
    expect(mutate).not.toHaveBeenCalled();
    expect(setTheme).toHaveBeenCalledWith('dark');
  });

  it('never rejects when the write fails, and keeps the local change', async () => {
    // `useApiMutation.mutate` RETHROWS. Propagating that would surface as an
    // unhandled rejection from an onClick handler — and a failed round-trip
    // must not cost the user the theme they can already see applied. The
    // failure is logged by the mutation hook, not swallowed silently.
    mutate.mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useThemeMode());
    await act(async () => {
      await expect(result.current.apply({ mode: 'dark', oled: true })).resolves.toBeUndefined();
    });
    expect(document.documentElement.hasAttribute('data-oled')).toBe(true);
    expect(setTheme).toHaveBeenCalledWith('dark');
  });

  it('recovers for the next press after a failed write', async () => {
    // The drain loop must not stay latched as "writing" after an error.
    mutate.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined);
    const { result } = renderHook(() => useThemeMode());
    await act(async () => {
      await result.current.apply({ mode: 'dark', oled: false });
    });
    mutate.mockClear();
    await act(async () => {
      await result.current.apply({ mode: 'light', oled: false });
    });
    expect(mutate).toHaveBeenCalledWith('/users/u1', { theme: 'light' });
  });
});

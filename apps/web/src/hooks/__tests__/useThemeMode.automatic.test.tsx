import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeModeProvider } from '@/lib/theme-preferences';
import { useThemeMode } from '../useThemeMode';
import { THEME_CLOCK_INTERVAL_MS, THEME_SCHEDULE_STORAGE_KEY } from '@/lib/theme-schedule';
import { OLED_STORAGE_KEY } from '@/lib/theme-mode';

const state = vi.hoisted(() => ({
  user: {
    id: 'owner',
    theme: 'auto',
    timezone: 'Europe/Paris',
    theme_light_start_minute: 420,
    theme_dark_start_minute: 1200,
  },
  setTheme: vi.fn(),
  mutate: vi.fn(),
  refreshUser: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: state.user, isLoading: false, refreshUser: state.refreshUser }),
}));
vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', resolvedTheme: 'light', setTheme: state.setTheme }),
}));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate: state.mutate }) }));

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-08T18:59:50Z'));
  vi.clearAllMocks();
  localStorage.clear();
  state.user = {
    id: 'owner',
    theme: 'auto',
    timezone: 'Europe/Paris',
    theme_light_start_minute: 420,
    theme_dark_start_minute: 1200,
  };
  state.mutate.mockResolvedValue(undefined);
});
afterEach(() => vi.useRealTimers());

describe('one automatic display owner', () => {
  it('keeps a failed local choice through a late profile read and clears its error for a new account', async () => {
    state.mutate.mockRejectedValueOnce(new Error('offline'));
    const { result, rerender } = renderHook(() => useThemeMode(), { wrapper: ThemeModeProvider });
    await act(async () => { await result.current.apply({ mode: 'dark', oled: true }); });
    state.user = { ...state.user, theme: 'light' };
    rerender();
    expect(document.documentElement).toHaveAttribute('data-oled');
    expect(result.current.saveError).toBe(true);
    state.user = { ...state.user, id: 'new-owner' };
    rerender();
    expect(document.documentElement).not.toHaveAttribute('data-oled');
    expect(result.current.saveError).toBe(false);
  });
  it('adopts an OLED choice made in another tab even when no schedule is stored', async () => {
    state.user = { ...state.user, theme: 'dark' };
    const { result } = renderHook(() => useThemeMode(), { wrapper: ThemeModeProvider });
    expect(result.current.oled).toBe(false);
    await act(async () => {
      localStorage.setItem(OLED_STORAGE_KEY, '1');
      window.dispatchEvent(new StorageEvent('storage', { key: OLED_STORAGE_KEY }));
    });
    expect(result.current.oled).toBe(true);
    expect(state.mutate).not.toHaveBeenCalled();
  });
  it('keeps an unsaved schedule in the next explicit preference write', async () => {
    state.mutate.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined);
    const { result } = renderHook(() => useThemeMode(), { wrapper: ThemeModeProvider });
    await act(async () => {
      await result.current.setSchedule({ lightStartMinute: 480, darkStartMinute: 1260 });
    });
    expect(result.current.saveError).toBe(true);
    await act(async () => {
      await result.current.apply({ mode: 'dark', oled: false });
    });
    expect(state.mutate).toHaveBeenLastCalledWith(
      '/users/owner',
      {
        theme: 'dark',
        theme_light_start_minute: 480,
        theme_dark_start_minute: 1260,
      },
      { signal: expect.any(AbortSignal) }
    );
    expect(result.current.saveError).toBe(false);
  });
  it('refuses a retained callback from a previous account', async () => {
    const { result, rerender } = renderHook(() => useThemeMode(), { wrapper: ThemeModeProvider });
    const previousApply = result.current.apply;
    state.user = { ...state.user, id: 'new-owner', theme: 'light' };
    rerender();
    state.setTheme.mockClear();
    await act(async () => {
      await previousApply({ mode: 'dark', oled: true });
    });
    expect(state.mutate).not.toHaveBeenCalled();
    expect(state.setTheme).not.toHaveBeenCalled();
    expect(document.documentElement).not.toHaveAttribute('data-oled');
  });

  it('refuses a retained callback after the provider unmounts', async () => {
    const { result, unmount } = renderHook(() => useThemeMode(), { wrapper: ThemeModeProvider });
    const apply = result.current.apply;
    unmount();
    state.setTheme.mockClear();
    await apply({ mode: 'dark', oled: true });
    expect(state.mutate).not.toHaveBeenCalled();
    expect(state.setTheme).not.toHaveBeenCalled();
  });
  it('shares a clock and crosses the boundary without a profile write', () => {
    const { result, unmount } = renderHook(() => [useThemeMode(), useThemeMode()], {
      wrapper: ThemeModeProvider,
    });
    expect(result.current.every(value => value.mode === 'auto')).toBe(true);
    const timers = vi.getTimerCount();
    act(() => {
      vi.advanceTimersByTime(THEME_CLOCK_INTERVAL_MS);
    });
    expect(state.setTheme).toHaveBeenLastCalledWith('dark');
    expect(document.documentElement).toHaveAttribute('data-oled');
    expect(state.mutate).not.toHaveBeenCalled();
    unmount();
    expect(vi.getTimerCount()).toBeLessThan(timers);
  });

  it('resolves immediately after sleep and after a backwards clock correction', () => {
    renderHook(() => useThemeMode(), { wrapper: ThemeModeProvider });
    act(() => {
      vi.setSystemTime(new Date('2026-11-09T01:00:00Z'));
      window.dispatchEvent(new Event('pageshow'));
    });
    expect(state.setTheme).toHaveBeenLastCalledWith('dark');
    act(() => {
      vi.setSystemTime(new Date('2026-11-08T12:00:00Z'));
      window.dispatchEvent(new Event('focus'));
    });
    expect(state.setTheme).toHaveBeenLastCalledWith('light');
  });

  it('leaves automatic mode when the person chooses a manual mode', async () => {
    const { result } = renderHook(() => useThemeMode(), { wrapper: ThemeModeProvider });
    await act(async () => {
      await result.current.apply({ mode: 'dark', oled: true });
    });
    expect(state.mutate).toHaveBeenCalledExactlyOnceWith(
      '/users/owner',
      { theme: 'oled' },
      { signal: expect.any(AbortSignal) }
    );
    expect(localStorage.getItem(THEME_SCHEDULE_STORAGE_KEY)).toBeNull();
    state.setTheme.mockClear();
    act(() => {
      vi.advanceTimersByTime(THEME_CLOCK_INTERVAL_MS);
    });
    expect(state.setTheme).not.toHaveBeenCalled();
  });

  it('ignores another account schedule in cross-tab storage events', () => {
    renderHook(() => useThemeMode(), { wrapper: ThemeModeProvider });
    localStorage.setItem(
      THEME_SCHEDULE_STORAGE_KEY,
      JSON.stringify({
        ownerId: 'stranger',
        timezone: 'UTC',
        lightStartMinute: 0,
        darkStartMinute: 1,
      })
    );
    state.setTheme.mockClear();
    act(() =>
      window.dispatchEvent(new StorageEvent('storage', { key: THEME_SCHEDULE_STORAGE_KEY }))
    );
    expect(state.setTheme).not.toHaveBeenCalled();
  });
});

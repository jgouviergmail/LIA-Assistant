'use client';

import {
  createContext,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { useTheme } from 'next-themes';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useAuth } from '@/hooks/useAuth';
import { useHydrated } from '@/hooks/useHydrated';
import { useThemeChoice } from '@/hooks/useThemeChoice';
import type { User } from './auth';
import {
  applyOledAttribute,
  fromPersistedTheme,
  readStoredOled,
  toPersistedTheme,
  withThemeTransition,
  writeStoredOled,
  OLED_STORAGE_KEY,
  type DisplayMode,
  type ThemeModeState,
  type TransitionOrigin,
} from './theme-mode';
import {
  automaticThemeAt,
  DEFAULT_DARK_START_MINUTE,
  DEFAULT_LIGHT_START_MINUTE,
  readThemeSchedule,
  THEME_CLOCK_INTERVAL_MS,
  THEME_SCHEDULE_STORAGE_KEY,
  writeThemeSchedule,
  type ThemeSchedule,
} from './theme-schedule';

interface ThemePatch {
  theme?: string;
  theme_light_start_minute?: number;
  theme_dark_start_minute?: number;
}

export interface ThemePreferences {
  mounted: boolean;
  mode: DisplayMode;
  resolved: 'light' | 'dark';
  oled: boolean;
  schedule: ThemeSchedule;
  saving: boolean;
  saveError: boolean;
  retrySave: () => Promise<void>;
  apply: (next: ThemeModeState, origin?: TransitionOrigin) => Promise<void>;
  setSchedule: (
    schedule: Pick<ThemeSchedule, 'lightStartMinute' | 'darkStartMinute'>
  ) => Promise<void>;
}

export const ThemePreferencesContext = createContext<ThemePreferences | null>(null);

function subscribeOled(changed: () => void): () => void {
  const observer = new MutationObserver(changed);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-oled'] });
  return () => observer.disconnect();
}
const currentOled = () => document.documentElement.hasAttribute('data-oled');
const serverOled = () => false;

/** One account synchronizer, write queue and clock for all display controls. */
export function ThemeModeProvider({ children }: { children: ReactNode }) {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const { user, refreshUser, isLoading } = useAuth();
  const userId = user?.id;
  const accountTheme = user?.theme;
  const accountLight = user?.theme_light_start_minute ?? DEFAULT_LIGHT_START_MINUTE;
  const accountDark = user?.theme_dark_start_minute ?? DEFAULT_DARK_START_MINUTE;
  const mounted = useHydrated();
  const oled = useSyncExternalStore(subscribeOled, currentOled, serverOled);
  const [saving, setSaving] = useState(false);
  const owner = useRef(userId);
  const previousOwner = useRef<string | undefined>(undefined);
  const desired = useRef<{ ownerId: string; patch: ThemePatch } | null>(null);
  const unsaved = useRef<ThemePatch>({});
  const writing = useRef(false);
  const active = useRef(true);
  const inFlight = useRef<AbortController | null>(null);
  const renderedMode = useRef(theme);
  const { mutate } = useApiMutation<ThemePatch, User>({
    method: 'PATCH',
    componentName: 'ThemeModeProvider',
  });
  const timezone = user?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  const { automatic, hours, saveError, setAutomatic, setHours, setSaveError } = useThemeChoice(
    {
      ownerId: userId,
      mode: accountTheme,
      lightStartMinute: accountLight,
      darkStartMinute: accountDark,
      timezone,
    },
    Boolean(isLoading),
    saving
  );
  const isCurrentOwner = useCallback(
    (id: string | undefined) => active.current && owner.current === id,
    []
  );

  useLayoutEffect(() => {
    owner.current = user?.id;
    if (desired.current?.ownerId !== user?.id) desired.current = null;
    unsaved.current = {};
    return () => {
      inFlight.current?.abort();
    };
  }, [user?.id]);
  useLayoutEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      desired.current = null;
      inFlight.current?.abort();
    };
  }, []);
  useLayoutEffect(() => {
    renderedMode.current = theme;
  }, [theme]);

  const draw = useCallback(
    (state: ThemeModeState) => {
      writeStoredOled(state.oled);
      if (document.documentElement.hasAttribute('data-oled') !== state.oled)
        applyOledAttribute(state.oled);
      if (state.mode !== 'auto' && state.mode !== renderedMode.current) {
        renderedMode.current = state.mode;
        setTheme(state.mode);
      }
    },
    [setTheme]
  );

  useEffect(() => {
    applyOledAttribute(readStoredOled());
  }, []);

  useEffect(() => {
    if (isLoading) return;
    const hadAccount = previousOwner.current === userId;
    const switched = previousOwner.current !== undefined && previousOwner.current !== userId;
    previousOwner.current = userId;
    if (!userId) {
      writeThemeSchedule(null);
      if (switched) draw({ mode: 'system', oled: false });
      return;
    }
    if ((writing.current || Object.keys(unsaved.current).length > 0) && !switched) return;
    const nextHours = {
      lightStartMinute: accountLight,
      darkStartMinute: accountDark,
    };
    const next = accountTheme === 'auto' ? { ...nextHours, timezone, ownerId: userId } : null;
    writeThemeSchedule(next);
    if (accountTheme && !next) {
      const saved = fromPersistedTheme(accountTheme);
      if (saved.mode !== 'system' || switched || hadAccount) draw(saved);
    }
  }, [userId, accountTheme, accountLight, accountDark, timezone, isLoading, draw]);

  useEffect(() => {
    if (!automatic) return;
    writeThemeSchedule({ ...automatic, timezone });
    const tick = () =>
      draw(
        automaticThemeAt(
          Date.now(),
          timezone,
          automatic.lightStartMinute,
          automatic.darkStartMinute
        )
      );
    tick();
    const timer = window.setInterval(tick, THEME_CLOCK_INTERVAL_MS);
    window.addEventListener('focus', tick);
    window.addEventListener('pageshow', tick);
    document.addEventListener('visibilitychange', tick);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', tick);
      window.removeEventListener('pageshow', tick);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [automatic, draw, timezone]);

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === OLED_STORAGE_KEY) {
        applyOledAttribute(readStoredOled());
        return;
      }
      if (event.key !== THEME_SCHEDULE_STORAGE_KEY) return;
      const stored = readThemeSchedule();
      if (stored && stored.ownerId !== owner.current) return;
      setAutomatic(stored);
      if (stored) setHours(stored);
      applyOledAttribute(readStoredOled());
    };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, [setAutomatic, setHours]);

  const persist = useCallback(
    async (ownerId: string, patch: ThemePatch) => {
      const merged = { ...unsaved.current, ...patch };
      unsaved.current = merged;
      desired.current = { ownerId, patch: merged };
      if (writing.current) return;
      writing.current = true;
      setSaving(true);
      setSaveError(false);
      try {
        while (desired.current && isCurrentOwner(desired.current.ownerId)) {
          const pending = desired.current;
          desired.current = null;
          const controller = new AbortController();
          inFlight.current = controller;
          let failed = false;
          try {
            await mutate(`/users/${pending.ownerId}`, pending.patch, { signal: controller.signal });
          } catch {
            failed = true;
          }
          if (isCurrentOwner(pending.ownerId)) {
            setSaveError(failed);
            if (!failed && unsaved.current === pending.patch) unsaved.current = {};
          }
        }
      } finally {
        writing.current = false;
        inFlight.current = null;
        if (active.current) setSaving(false);
      }
      if (isCurrentOwner(ownerId)) await refreshUser?.();
    },
    [mutate, refreshUser, isCurrentOwner, setSaveError]
  );

  const apply = useCallback(
    async (next: ThemeModeState, origin?: TransitionOrigin) => {
      if (!isCurrentOwner(user?.id)) return;
      const stored = next.mode === 'auto' && user ? { ...hours, timezone, ownerId: user.id } : null;
      setAutomatic(stored);
      writeThemeSchedule(stored);
      withThemeTransition(
        () =>
          draw(
            stored
              ? automaticThemeAt(
                  Date.now(),
                  timezone,
                  stored.lightStartMinute,
                  stored.darkStartMinute
                )
              : next
          ),
        origin
      );
      if (user) await persist(user.id, { theme: toPersistedTheme(next) });
    },
    [user, hours, timezone, draw, persist, isCurrentOwner, setAutomatic]
  );

  const setSchedule = useCallback(
    async (next: Pick<ThemeSchedule, 'lightStartMinute' | 'darkStartMinute'>) => {
      if (!isCurrentOwner(user?.id)) return;
      automaticThemeAt(Date.now(), timezone, next.lightStartMinute, next.darkStartMinute);
      setHours(next);
      if (automatic && user) {
        const stored = { ...next, timezone, ownerId: user.id };
        setAutomatic(stored);
        writeThemeSchedule(stored);
      }
      if (user)
        await persist(user.id, {
          theme_light_start_minute: next.lightStartMinute,
          theme_dark_start_minute: next.darkStartMinute,
        });
    },
    [automatic, user, timezone, persist, isCurrentOwner, setAutomatic, setHours]
  );

  const mode: DisplayMode = automatic
    ? 'auto'
    : theme === 'dark' || theme === 'light'
      ? theme
      : 'system';
  return (
    <ThemePreferencesContext.Provider
      value={{
        mounted,
        mode,
        resolved: resolvedTheme === 'dark' ? 'dark' : 'light',
        oled,
        schedule: { ...hours, timezone },
        saving,
        saveError,
        retrySave: async () => {
          if (userId && isCurrentOwner(userId)) await persist(userId, {});
        },
        apply,
        setSchedule,
      }}
    >
      {children}
    </ThemePreferencesContext.Provider>
  );
}

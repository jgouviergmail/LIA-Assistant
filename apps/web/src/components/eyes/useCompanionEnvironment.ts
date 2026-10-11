'use client';

import { useEffect } from 'react';
import apiClient from '@/lib/api-client';
import { useCompanionEnvironmentStore } from '@/stores/companionEnvironmentStore';
import { parseEnvironment, weatherFlagsAt, type CompanionEnvironment } from './environment';

const REFRESH_MS = 15 * 60_000;

/** Reuse the owner's one timer for freshness boundaries, not extra provider reads. */
function nextWakeAt(context: CompanionEnvironment | null, requestAt: number, now: number) {
  const observedAt = Date.parse(context?.weather?.observed_at ?? '');
  const expiresAt = Date.parse(context?.weather?.expires_at ?? '');
  return Math.min(
    requestAt,
    observedAt > now ? observedAt : Infinity,
    expiresAt > now ? expiresAt : Infinity
  );
}

/** One owner; cached weather only, suspended off-page and cleared on unmount. */
export function useCompanionEnvironment(enabled: boolean): void {
  useEffect(() => {
    const store = useCompanionEnvironmentStore.getState();
    store.reset();
    if (!enabled) return;
    let disposed = false;
    let generation = 0;
    let nextRequestAt = 0;
    let controller: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let announcedFlags = weatherFlagsAt(null, Date.now());
    const syncObservation = () => {
      const context = useCompanionEnvironmentStore.getState().environment;
      const now = Date.now();
      if (context?.weather && now >= Date.parse(context.weather.expires_at)) {
        announcedFlags = weatherFlagsAt(null, now);
        store.setEnvironment({ ...context, weather: null });
        return;
      }
      const flags = weatherFlagsAt(context, now);
      if (flags === announcedFlags) return;
      announcedFlags = flags;
      if (context) store.setEnvironment(context);
    };
    const cancelTimer = () => {
      if (timer !== null) clearTimeout(timer);
      timer = null;
    };
    const schedule = () => {
      cancelTimer();
      if (!disposed && !document.hidden) {
        const now = Date.now();
        const wakeAt = nextWakeAt(
          useCompanionEnvironmentStore.getState().environment,
          controller && now >= nextRequestAt ? Infinity : nextRequestAt,
          now
        );
        if (Number.isFinite(wakeAt)) timer = setTimeout(refresh, Math.max(0, wakeAt - now));
      }
    };
    const refresh = async () => {
      if (disposed || document.hidden) return;
      syncObservation();
      if (Date.now() < nextRequestAt || controller) {
        schedule();
        return;
      }
      const request = ++generation;
      controller = new AbortController();
      nextRequestAt = Date.now() + REFRESH_MS;
      schedule();
      try {
        const payload = await apiClient.get<unknown>('/briefing/companion-context', {
          signal: controller.signal,
          timeout: 5000,
        });
        if (!disposed && request === generation) {
          const context = parseEnvironment(payload);
          if (context) {
            announcedFlags = weatherFlagsAt(context, Date.now());
            store.setEnvironment(context);
          }
          syncObservation();
        }
      } catch {
        // A failed read is no new evidence; the original deadline remains authoritative.
        if (!disposed && request === generation) syncObservation();
      } finally {
        if (request === generation) {
          controller = null;
          schedule();
        }
      }
    };
    const pause = () => {
      cancelTimer();
      generation++;
      if (controller) nextRequestAt = 0;
      controller?.abort();
      controller = null;
    };
    const visibility = () => {
      if (document.hidden) pause();
      else void refresh();
    };
    document.addEventListener('visibilitychange', visibility);
    void refresh();
    return () => {
      disposed = true;
      pause();
      document.removeEventListener('visibilitychange', visibility);
      store.reset();
    };
  }, [enabled]);
}

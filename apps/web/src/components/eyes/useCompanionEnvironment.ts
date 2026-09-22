'use client';

import { useEffect } from 'react';
import apiClient from '@/lib/api-client';
import { useCompanionEnvironmentStore } from '@/stores/companionEnvironmentStore';
import { parseEnvironment } from './environment';

const REFRESH_MS = 15 * 60_000;

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
    const cancelTimer = () => {
      if (timer !== null) clearTimeout(timer);
      timer = null;
    };
    const schedule = () => {
      cancelTimer();
      if (!disposed && !document.hidden)
        timer = setTimeout(refresh, Math.max(0, nextRequestAt - Date.now()));
    };
    const refresh = async () => {
      if (disposed || document.hidden || controller) return;
      if (Date.now() < nextRequestAt) {
        schedule();
        return;
      }
      const request = ++generation;
      controller = new AbortController();
      nextRequestAt = Date.now() + REFRESH_MS;
      try {
        const payload = await apiClient.get<unknown>('/briefing/companion-context', {
          signal: controller.signal,
          timeout: 5000,
        });
        if (!disposed && request === generation) store.setEnvironment(parseEnvironment(payload));
      } catch {
        if (!disposed && request === generation) store.reset();
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

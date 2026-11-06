'use client';

/**
 * A tool's re-read (ADR-369): the person's button, and the return to the page.
 *
 * What an open tool shows is read once, and a provider changes it behind the
 * screen: « Refresh » re-reads it, and coming back to the page after a while
 * does too, unasked. An unasked re-read says so, so it can take nothing away.
 * The two return signals (`focus`, `visibilitychange`) usually come together:
 * the time since the last read makes them one, and bounds what a person going
 * back and forth between two windows costs the provider.
 */
import { useEffect, useEffectEvent, useRef, useState } from 'react';

import { WORKBENCH_RETURN_REREAD_MIN_MS } from '@/lib/workbench/tools';
import type { RereadOptions } from '@/lib/workbench/types';

/** Re-reads what a screen shows; a failure is the screen's own to say, never a rejection. */
export type ToolRefresh = (options: Required<RereadOptions>) => Promise<unknown>;

export interface ToolRefreshState {
  /** A re-read the person asked for is on its way. */
  refreshing: boolean;
  refresh: () => Promise<void>;
}

export function useToolRefresh(onRefresh: ToolRefresh | undefined): ToolRefreshState {
  const [refreshing, setRefreshing] = useState(false);
  const lastRead = useRef(0);

  const refresh = async () => {
    if (!onRefresh || refreshing) return;
    lastRead.current = Date.now();
    setRefreshing(true);
    try {
      await onRefresh({ unasked: false });
    } finally {
      setRefreshing(false);
    }
  };

  const reread = useEffectEvent(() => {
    if (!onRefresh || document.visibilityState !== 'visible') return;
    if (Date.now() - lastRead.current < WORKBENCH_RETURN_REREAD_MIN_MS) return;
    lastRead.current = Date.now();
    void onRefresh({ unasked: true });
  });

  useEffect(() => {
    lastRead.current = Date.now();
    const onReturn = () => reread();
    window.addEventListener('focus', onReturn);
    document.addEventListener('visibilitychange', onReturn);
    return () => {
      window.removeEventListener('focus', onReturn);
      document.removeEventListener('visibilitychange', onReturn);
    };
  }, []);

  return { refreshing, refresh };
}

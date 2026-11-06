'use client';

/**
 * What the mailbox leaves unread, kept fresh for the rail and the folder pane
 * (ADR-369, lot 4).
 *
 * The figures are polled, the listings never are: a provider counts them in one small
 * call, a listing reads every row. A hidden page reads nothing, and coming back to it
 * reads at once. A read state changed here moves the figure on the spot, so that
 * reading through a folder costs the provider no call; a message sent elsewhere reads
 * the figures again, since only the provider knows what it left unread.
 */
import { useCallback, useEffect } from 'react';

import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import type { MailCounts } from '@/lib/workbench/types';

const COUNTS_PATH = '/workbench/mail/counts';
/** How often a visible page asks. */
export const MAIL_COUNTS_EVERY_MS = 120_000;

export interface MailCountsState {
  /** Each folder's figure, by its id in the pane; undefined until read. */
  counts: Readonly<Record<string, number>> | undefined;
  /** Moves one figure on the spot, never below zero. */
  adjust: (folder: string, delta: number) => void;
  /** Reads the figures again; a failure leaves the last ones. */
  reread: () => void;
}

/** @param enabled - Whether a mail provider is ready (nothing is read otherwise). */
export function useMailCounts(enabled: boolean): MailCountsState {
  const query = useApplicationAccountQuery<MailCounts>(COUNTS_PATH, 'WorkbenchMail', enabled);
  const { refetch, setData } = query;

  const reread = useCallback(() => {
    void refetch().catch(() => undefined);
  }, [refetch]);

  useEffect(() => {
    if (!enabled) return;
    const readWhenSeen = () => {
      if (document.visibilityState === 'visible') reread();
    };
    const timer = window.setInterval(readWhenSeen, MAIL_COUNTS_EVERY_MS);
    document.addEventListener('visibilitychange', readWhenSeen);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', readWhenSeen);
    };
  }, [enabled, reread]);

  const adjust = useCallback(
    (folder: string, delta: number) => {
      setData(current => {
        const figure = current?.counts[folder];
        if (!current || figure === undefined) return current;
        return { ...current, counts: { ...current.counts, [folder]: Math.max(0, figure + delta) } };
      });
    },
    [setData]
  );

  return { counts: query.data?.counts, adjust, reread };
}

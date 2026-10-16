'use client';

/**
 * LIA's voices for one person (ADR-345 amendment 2026-10-14): read once, and
 * saved whole — both genders in one request, so a save never undoes the other
 * gender's. The hook adopts what the server answered: it decides what a choice
 * now reads as.
 */

import { useCallback, useRef } from 'react';

import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import apiClient from '@/lib/api-client';
import type { LiaVoiceChoice, LiaVoices } from '@/types/lia-voices';

export const LIA_VOICES_ENDPOINT = '/voice/lia-voices';

export interface UseLiaVoices {
  lia: LiaVoices | undefined;
  loading: boolean;
  error: Error | null;
  /** Keep both voices (a refusal rejects with the API's coded error). */
  save: (choice: LiaVoiceChoice) => Promise<void>;
}

export function useLiaVoices(): UseLiaVoices {
  const { data, loading, error, setData, lifetime, isCurrent } =
    useApplicationAccountQuery<LiaVoices>(LIA_VOICES_ENDPOINT, 'LiaVoicesFields');
  const queues = useRef(new Map<typeof lifetime, Promise<void>>());

  const save = useCallback(
    async (choice: LiaVoiceChoice): Promise<void> => {
      const queued = queues.current.get(lifetime) ?? Promise.resolve();
      const writing = queued.then(async () => {
        if (!isCurrent()) throw new DOMException('Account lifetime ended', 'AbortError');
        const saved = await apiClient.put<LiaVoices>(LIA_VOICES_ENDPOINT, choice);
        if (!isCurrent()) throw new DOMException('Account lifetime ended', 'AbortError');
        setData(saved);
      });
      // Keep the queue usable after a refusal; its caller still receives the
      // original rejecting promise. Each subsequent save is an explicit choice.
      const settled = writing.catch(() => undefined);
      queues.current.set(lifetime, settled);
      try {
        await writing;
      } finally {
        if (queues.current.get(lifetime) === settled) queues.current.delete(lifetime);
      }
    },
    [setData, lifetime, isCurrent]
  );

  return { lia: data, loading, error, save };
}

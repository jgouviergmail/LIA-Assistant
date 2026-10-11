'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import type { User } from '@/lib/auth';

export interface LastLocationView {
  stored: boolean;
  lat: number | null;
  lon: number | null;
  accuracy: number | null;
  updated_at: string | null;
  stale: boolean;
}

/** Late or foreign replies cannot replace the current account's saved position. */
export function useSavedLastLocation(user: User | null, optedIn: boolean) {
  const [reply, setReply] = useState<{ owner: User; value: LastLocationView } | null>(null);
  const [readFailure, setReadFailure] = useState<User | null>(null);
  const readSequence = useRef(0);
  const activeOwner = useRef(user?.id);
  const stored = reply && reply.owner === user ? reply.value : null;
  const clearStored = useCallback(() => {
    if (!user || activeOwner.current !== user.id) return;
    readSequence.current += 1;
    setReply(null);
  }, [user]);

  const fetchStored = useCallback(async () => {
    if (!user) return;
    const sequence = ++readSequence.current;
    try {
      const data = await apiClient.get<LastLocationView>('/auth/me/last-location');
      if (sequence !== readSequence.current) return;
      setReply({ owner: user, value: data });
      setReadFailure(null);
    } catch (err) {
      logger.warn('last_known_location_stored_fetch_failed', {
        component: 'LastKnownLocationSection',
        error: String(err),
      });
      if (sequence === readSequence.current) setReadFailure(user);
      throw err;
    }
  }, [user]);

  // Initial fetch + refresh after toggle.
  useEffect(() => {
    activeOwner.current = user?.id;
    const sequence = readSequence.current;
    // Finish Strict Mode setup/cleanup before IO, matching the shared query owner.
    queueMicrotask(() => {
      if (optedIn && sequence === readSequence.current) void fetchStored().catch(() => {});
    });
    return () => { readSequence.current += 1; activeOwner.current = undefined; };
  }, [optedIn, fetchStored, user?.id]);
  const releaseRead = useCallback(() => {}, []);
  useApplicationResourceSync(optedIn ? user?.id : undefined, 'locations', fetchStored, releaseRead);

  return { stored: optedIn ? stored : null, readFailed: !!user && readFailure === user, clearStored };
}

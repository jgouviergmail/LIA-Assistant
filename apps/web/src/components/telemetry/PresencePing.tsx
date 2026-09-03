'use client';

/**
 * Reading presence (ADR-214 amendment, 2026-09-03) — renders nothing.
 *
 * Tells the API "the user has LIA in front of them": on mount, when the
 * document becomes visible again and on window focus, throttled client-side
 * so a busy tab sends at most one ping per throttle window. NEVER from a
 * background poll — an open tab on a second screen is not a presence — and
 * only for an authenticated user. The server banks at most one activity hour
 * per local hour, so a lost or duplicated ping costs nothing. Silent on any
 * failure: presence is learning material, never a user-facing feature.
 */

import { useEffect, useRef } from 'react';

import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';

const DEFAULT_THROTTLE_MINUTES = 15;

function throttleMs(): number {
  const raw = Number(process.env.NEXT_PUBLIC_PRESENCE_THROTTLE_MINUTES ?? DEFAULT_THROTTLE_MINUTES);
  const minutes = Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_THROTTLE_MINUTES;
  return minutes * 60_000;
}

export function PresencePing(): null {
  const { user, isLoading } = useAuth();
  const lastSentAt = useRef(0);
  const authenticated = !isLoading && user !== null;

  useEffect(() => {
    if (!authenticated) return undefined;

    const send = () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
      const now = Date.now();
      if (now - lastSentAt.current < throttleMs()) return;
      lastSentAt.current = now;
      void apiClient.post('/habits/presence').catch(() => undefined);
    };

    send();
    document.addEventListener('visibilitychange', send);
    window.addEventListener('focus', send);
    return () => {
      document.removeEventListener('visibilitychange', send);
      window.removeEventListener('focus', send);
    };
  }, [authenticated]);

  return null;
}

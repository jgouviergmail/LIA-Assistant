'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { getApiErrorCode } from '@/lib/api-error';
import { GEOLOCATION_ENABLED_KEY } from '@/lib/constants';
import { readGrantedPosition } from '@/lib/browser-geolocation';
import { parsePlaceRoute, type PlaceRoute } from '@/lib/place-route-data';
import type { MapPoint } from '@/lib/route-map-data';
import {
  useApplicationAccountLifetime,
  type ApplicationAccountLifetime,
} from './useApplicationAccountLifetime';

const CACHE_MS = 120_000;
const CACHE_LIMIT = 16;
interface RouteState {
  status: 'idle' | 'loading' | 'ready' | 'error';
  ref: string | null;
  result: PlaceRoute | null;
  error: 'origin' | 'request' | null;
}
const idle: RouteState = { status: 'idle', ref: null, result: null, error: null };
type RouteCache = Map<
  string,
  { lifetime: ApplicationAccountLifetime; at: number; result: PlaceRoute }
>;

function cachedRoute(
  cache: RouteCache,
  key: string,
  lifetime: ApplicationAccountLifetime,
  force: boolean
) {
  if (force) return null;
  const cached = cache.get(key);
  return cached?.lifetime === lifetime && Date.now() - cached.at < CACHE_MS ? cached.result : null;
}

function rememberRoute(
  cache: RouteCache,
  key: string,
  lifetime: ApplicationAccountLifetime,
  result: PlaceRoute
) {
  cache.delete(key);
  cache.set(key, { lifetime, at: Date.now(), result });
  if (cache.size > CACHE_LIMIT) {
    const first = cache.keys().next().value;
    if (first !== undefined) cache.delete(first);
  }
}

function locationEnabled() {
  try {
    return localStorage.getItem(GEOLOCATION_ENABLED_KEY) === 'true';
  } catch {
    return false;
  }
}

async function currentOrigin(signal: AbortSignal) {
  return locationEnabled() ? readGrantedPosition(signal) : null;
}

function routeCacheKey(selection: string, origin: Awaited<ReturnType<typeof currentOrigin>>) {
  return `${selection}:${origin ? `${origin.lat}:${origin.lon}` : 'fallback'}`;
}

async function fetchSelectedRoute(
  destination: MapPoint,
  origin: Awaited<ReturnType<typeof currentOrigin>>,
  signal: AbortSignal
) {
  const raw = await apiClient.post<unknown>(
    '/connectors/google-maps/place-route',
    { destination, ...(origin ? { origin } : {}) },
    { signal, timeout: 35_000 }
  );
  const result = parsePlaceRoute(raw);
  if (!result) throw new Error('Invalid place route response');
  return result;
}

/** Explicit selections own their transport, result and short-lived account-local cache. */
export function usePlaceRoute(owner: string | null) {
  const { lifetime, isCurrent } = useApplicationAccountLifetime(owner ?? undefined);
  const [snapshot, setSnapshot] = useState({ lifetime, state: idle });
  const sequence = useRef(0);
  const request = useRef<AbortController | null>(null);
  const pending = useRef<string | null>(null);
  const cache = useRef<RouteCache>(new Map());
  useEffect(
    () => () => {
      sequence.current++;
      request.current?.abort();
      pending.current = null;
      cache.current.clear();
    },
    [lifetime]
  );

  const load = useCallback(
    async (ref: string, destination: MapPoint, force = false) => {
      if (!isCurrent()) return null;
      const selection = `${ref}:${destination.lat}:${destination.lng}`;
      if (pending.current === selection && !force) return null;
      const own = ++sequence.current;
      request.current?.abort();
      const abort = new AbortController();
      request.current = abort;
      pending.current = selection;
      const current = () => isCurrent() && own === sequence.current && !abort.signal.aborted;
      setSnapshot({ lifetime, state: { status: 'loading', ref, result: null, error: null } });
      try {
        const origin = await currentOrigin(abort.signal);
        if (!current()) return null;
        const key = routeCacheKey(selection, origin);
        const cached = cachedRoute(cache.current, key, lifetime, force);
        if (cached) {
          setSnapshot({ lifetime, state: { status: 'ready', ref, result: cached, error: null } });
          return cached;
        }
        const result = await fetchSelectedRoute(destination, origin, abort.signal);
        if (!current()) return null;
        rememberRoute(cache.current, key, lifetime, result);
        setSnapshot({ lifetime, state: { status: 'ready', ref, result, error: null } });
        return result;
      } catch (error) {
        if (current())
          setSnapshot({
            lifetime,
            state: {
              status: 'error',
              ref,
              result: null,
              error:
                getApiErrorCode(error) === 'place_route_origin_unavailable' ? 'origin' : 'request',
            },
          });
        return null;
      } finally {
        if (own === sequence.current) pending.current = null;
      }
    },
    [isCurrent, lifetime]
  );
  return { state: snapshot.lifetime === lifetime ? snapshot.state : idle, load };
}

/**
 * Global throttled push of the browser position to the backend.
 *
 * Feeds the generalized last-known location (2026-08-16): whenever the user
 * opted in (`use_last_known_location`), browser geolocation is enabled and
 * fresh coordinates exist, the position is PUT to /auth/me/last-location at
 * most once per throttle window. Mounted in the authenticated shell — the
 * pre-generalization version lived inside the weather settings block and
 * only ran while that settings page was open, so in real mobility nothing
 * ever fed the backend.
 *
 * Return-to-foreground needs no listener here: `useGeolocation` refreshes
 * its coordinates on `visibilitychange`/`pageshow`, which re-runs the push
 * effect through the `coordinates` dependency.
 */

import { useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useGeolocation } from '@/hooks/useGeolocation';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { LAST_LOCATION_PUSH_THROTTLE_MS, LAST_LOCATION_PUSH_TS_KEY } from '@/lib/constants';

/** Pre-generalization marker written by the removed weather settings block. */
const LEGACY_PUSH_TS_KEY = 'smart_weather_last_push_ms';

export function useLastKnownLocationSync(): void {
  const { user } = useAuth();
  const { coordinates, isEnabled } = useGeolocation();

  // One-time cleanup of the weather-scoped marker so it does not linger
  // forever in existing browsers.
  useEffect(() => {
    try {
      localStorage.removeItem(LEGACY_PUSH_TS_KEY);
    } catch {
      // Storage unavailable — nothing to clean.
    }
  }, []);

  useEffect(() => {
    if (!user?.use_last_known_location || !isEnabled || !coordinates) return;

    let lastPush = 0;
    try {
      lastPush = Number.parseInt(localStorage.getItem(LAST_LOCATION_PUSH_TS_KEY) ?? '0', 10) || 0;
    } catch {
      lastPush = 0;
    }
    if (Date.now() - lastPush < LAST_LOCATION_PUSH_THROTTLE_MS) return;

    (async () => {
      try {
        await apiClient.put('/auth/me/last-location', {
          lat: coordinates.lat,
          lon: coordinates.lon,
          accuracy: coordinates.accuracy,
        });
        try {
          localStorage.setItem(LAST_LOCATION_PUSH_TS_KEY, String(Date.now()));
        } catch {
          // Best effort: an unwritable marker only means an extra push later.
        }
        logger.debug('last_known_location_pushed', {
          component: 'useLastKnownLocationSync',
        });
      } catch (err) {
        // No throttle stamp on failure: the next coordinates change retries
        // instead of going silent for a whole window after a transient error.
        logger.debug('last_known_location_push_failed', {
          component: 'useLastKnownLocationSync',
          error: String(err),
        });
      }
    })();
  }, [user?.use_last_known_location, isEnabled, coordinates]);
}

export default useLastKnownLocationSync;

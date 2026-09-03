/**
 * Best-effort position at recording start (ADR-258).
 *
 * The minutes carry the place when it is known. The rule here is "never ask":
 * the position is read only when the browser ALREADY granted geolocation (the
 * permission was the user's decision elsewhere — the location settings, ADR-219),
 * with a short timeout so a slow GPS never delays the first second of capture.
 */

import type { MeetingGeolocation } from '@/types/meetings';

/** Longest wait for a fix before recording without a position. */
const POSITION_TIMEOUT_MS = 3000;

async function permissionGranted(): Promise<boolean> {
  if (typeof navigator === 'undefined' || !navigator.permissions?.query) return false;
  try {
    const status = await navigator.permissions.query({ name: 'geolocation' });
    return status.state === 'granted';
  } catch {
    return false;
  }
}

/**
 * The current position when geolocation is already granted, else `null`.
 *
 * @returns Latitude/longitude/accuracy, or `null` (never a prompt, never a throw).
 */
export async function bestEffortPosition(): Promise<MeetingGeolocation | null> {
  if (typeof navigator === 'undefined' || !navigator.geolocation) return null;
  if (!(await permissionGranted())) return null;
  return new Promise(resolve => {
    const timer = setTimeout(() => resolve(null), POSITION_TIMEOUT_MS);
    navigator.geolocation.getCurrentPosition(
      position => {
        clearTimeout(timer);
        resolve({
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          accuracy_m: Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null,
        });
      },
      () => {
        clearTimeout(timer);
        resolve(null);
      },
      { maximumAge: 60_000, timeout: POSITION_TIMEOUT_MS, enableHighAccuracy: false }
    );
  });
}

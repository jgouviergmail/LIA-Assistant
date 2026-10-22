/**
 * Best-effort position at recording start (ADR-258).
 *
 * The minutes carry the place when it is known. The rule here is "never ask":
 * the position is read only when the browser ALREADY granted geolocation (the
 * permission was the user's decision elsewhere — the location settings, ADR-219),
 * with a short timeout so a slow GPS never delays the first second of capture.
 */

import type { MeetingGeolocation } from '@/types/meetings';
import { readGrantedPosition } from '@/lib/browser-geolocation';

/**
 * The current position when geolocation is already granted, else `null`.
 *
 * @returns Latitude/longitude/accuracy, or `null` (never a prompt, never a throw).
 */
export async function bestEffortPosition(): Promise<MeetingGeolocation | null> {
  const position = await readGrantedPosition();
  return position ? { lat: position.lat, lon: position.lon, accuracy_m: position.accuracy } : null;
}

'use client';

/**
 * The screen the reader came from, as it travelled in the URL.
 *
 * One reader for `?from=`, so the three meeting pages cannot spell the
 * parameter three ways. The value is a TOKEN of the dashboard's destination
 * table and is never trusted as a route: `backDestination` resolves it, and
 * anything unrecognised falls back to the chat (`lib/back-origin.ts`).
 */

import { useSearchParams } from 'next/navigation';

/** Query parameter carrying the origin. */
export const ORIGIN_PARAM = 'from';

/**
 * The raw origin token, or null when the reader arrived without one.
 *
 * @returns The `?from=` value as written, never resolved — the caller decides
 *   whether it wants a destination (`backDestination`) or wants to carry it
 *   forward (`withOrigin`).
 */
export function useBackOrigin(): string | null {
  return useSearchParams().get(ORIGIN_PARAM);
}

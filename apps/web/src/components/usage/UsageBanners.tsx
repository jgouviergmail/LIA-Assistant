'use client';

/**
 * The quota surface of the chat, in one place (A5).
 *
 * Two banners describe the same subject and must NEVER appear together: the
 * warning that precedes the wall, and the wall itself. Leaving that rule in the
 * page meant two independent conditions sitting next to each other, one of them
 * relying on `usageWarningOf` returning null while blocked — true, but invisible
 * from the call site, and one edit away from a page that shouts twice about the
 * same limit at the worst possible moment.
 *
 * Extracting it also keeps the chat page under its complexity cap (the
 * shrink-only F011 ratchet), which is the honest reason to split rather than to
 * grow a hotspot.
 */

import { useMemo } from 'react';

import { UsageBlockedBanner } from './UsageBlockedBanner';
import { UsageWarningBanner } from './UsageWarningBanner';
import { usageWarningOf } from '@/lib/usage-warning';
import type { UserUsageLimitResponse } from '@/types/usage-limits';

export interface UsageBannersProps {
  /** Full `/usage-limits/me` payload, or null when the feature is off. */
  limits: UserUsageLimitResponse | null;
  /** Whether the account is currently blocked (any reason). */
  isBlocked: boolean;
  /** Reason shown by the blocking banner. */
  blockReason: string | null;
}

export function UsageBanners({ limits, isBlocked, blockReason }: UsageBannersProps) {
  const warning = useMemo(() => usageWarningOf(limits), [limits]);

  // Blocked wins, always: the wall is the state, the warning was its forecast.
  if (isBlocked) return <UsageBlockedBanner blockReason={blockReason} />;
  return warning ? <UsageWarningBanner warning={warning} /> : null;
}

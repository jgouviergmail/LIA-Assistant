'use client';

import type { ContextUsage } from '@/types/chat-state';
import { ContextUsagePill, type ConversationTotalsDisplay } from './ContextUsagePill';

/** Keep the native cost opt-in when sharing the conversation workspace. */
export function ChatContextUsage({
  usage,
  enabled,
  totals,
}: {
  usage: ContextUsage | null;
  enabled: boolean;
  totals: ConversationTotalsDisplay;
}) {
  if (!usage) return null;
  const showTotals = enabled && (totals.tokensIn > 0 || totals.tokensOut > 0);
  return <ContextUsagePill usage={usage} totals={showTotals ? totals : null} />;
}

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
  totals: ConversationTotalsDisplay | null;
}) {
  if (!usage) return null;
  return <ContextUsagePill usage={usage} totals={enabled ? totals : null} />;
}

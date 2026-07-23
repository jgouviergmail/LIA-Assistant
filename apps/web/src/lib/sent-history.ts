/**
 * Sent-history extraction for the chat input ↑/↓ recall walk
 * (UXR Lot 2 A7, extended per QA feedback 2026-07-23).
 */

import { CHAT_SENT_HISTORY_MAX } from '@/lib/constants';
import type { Message } from '@/types/chat';

/**
 * Past sent user messages, NEWEST FIRST, consecutive duplicates collapsed,
 * capped at CHAT_SENT_HISTORY_MAX.
 */
export function sentHistoryOf(messages: Message[]): string[] {
  const out: string[] = [];
  for (let i = messages.length - 1; i >= 0 && out.length < CHAT_SENT_HISTORY_MAX; i--) {
    const m = messages[i];
    if (m.role === 'user' && out[out.length - 1] !== m.content) out.push(m.content);
  }
  return out;
}

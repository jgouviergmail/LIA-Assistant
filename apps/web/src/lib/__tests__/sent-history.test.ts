/**
 * sentHistoryOf — the ↑/↓ recall walk's data source (UXR A7 extended,
 * QA 2026-07-23): newest first, consecutive dups collapsed, capped.
 */

import { describe, it, expect } from 'vitest';

import { sentHistoryOf } from '@/lib/sent-history';
import { CHAT_SENT_HISTORY_MAX } from '@/lib/constants';
import type { Message } from '@/types/chat';

function msg(role: 'user' | 'assistant', content: string, i: number): Message {
  return { id: `m${i}`, role, content, timestamp: new Date(0) };
}

describe('sentHistoryOf', () => {
  it('returns user messages newest first, skipping assistant turns', () => {
    const messages = [
      msg('user', 'premier', 1),
      msg('assistant', 'réponse', 2),
      msg('user', 'second', 3),
    ];
    expect(sentHistoryOf(messages)).toEqual(['second', 'premier']);
  });

  it('collapses consecutive duplicate sends into one entry', () => {
    const messages = [
      msg('user', 'oui', 1),
      msg('assistant', 'ok', 2),
      msg('user', 'oui', 3),
      msg('user', 'autre', 4),
    ];
    expect(sentHistoryOf(messages)).toEqual(['autre', 'oui']);
  });

  it('caps at CHAT_SENT_HISTORY_MAX entries', () => {
    const messages = Array.from({ length: CHAT_SENT_HISTORY_MAX + 5 }, (_, i) =>
      msg('user', `message ${i}`, i)
    );
    const history = sentHistoryOf(messages);
    expect(history).toHaveLength(CHAT_SENT_HISTORY_MAX);
    expect(history[0]).toBe(`message ${CHAT_SENT_HISTORY_MAX + 4}`);
  });

  it('returns empty for a conversation without user messages', () => {
    expect(sentHistoryOf([msg('assistant', 'bonjour', 1)])).toEqual([]);
    expect(sentHistoryOf([])).toEqual([]);
  });
});

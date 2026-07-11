/**
 * getLastAssistantMessageId — drives which row animates its psyche emoji (spec D-5).
 */

import { describe, it, expect } from 'vitest';

import { getLastAssistantMessageId } from '../ChatMessageList';
import type { Message } from '@/types/chat';

function msg(id: string, role: Message['role']): Message {
  return { id, role, content: 'x', timestamp: new Date(0) } as Message;
}

describe('getLastAssistantMessageId', () => {
  it('returns the id of the last assistant message', () => {
    const messages = [
      msg('u1', 'user'),
      msg('a1', 'assistant'),
      msg('u2', 'user'),
      msg('a2', 'assistant'),
    ];
    expect(getLastAssistantMessageId(messages)).toBe('a2');
  });

  it('ignores trailing user and system messages', () => {
    const messages = [msg('a1', 'assistant'), msg('s1', 'system'), msg('u1', 'user')];
    expect(getLastAssistantMessageId(messages)).toBe('a1');
  });

  it('returns null when there is no assistant message', () => {
    expect(getLastAssistantMessageId([msg('u1', 'user')])).toBeNull();
    expect(getLastAssistantMessageId([])).toBeNull();
  });
});

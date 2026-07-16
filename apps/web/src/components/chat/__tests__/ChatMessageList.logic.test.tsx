/**
 * ChatMessageList — the exported pure helpers: time-of-day greeting and
 * last-assistant-message lookup.
 */

import { describe, it, expect } from 'vitest';

import { greetingForHour, getLastAssistantMessageId } from '../ChatMessageList';
import type { Message } from '@/types/chat';

function msg(id: string, role: Message['role']): Message {
  return { id, role, content: '', timestamp: new Date(0) };
}

describe('greetingForHour', () => {
  it.each<[number, string, boolean]>([
    [0, '😴', true],
    [4, '😴', true],
    [23, '😴', true],
    [5, '☕', false],
    [10, '☕', false],
    [11, '👋', false],
    [17, '👋', false],
    [18, '🌛', false],
    [22, '🌛', false],
  ])('hour %i maps to %s', (hour, glyph, isNight) => {
    expect(greetingForHour(hour)).toEqual({ glyph, isNight });
  });
});

describe('getLastAssistantMessageId', () => {
  it('returns the id of the last assistant message', () => {
    const messages = [
      msg('1', 'user'),
      msg('2', 'assistant'),
      msg('3', 'assistant'),
      msg('4', 'user'),
    ];
    expect(getLastAssistantMessageId(messages)).toBe('3');
  });

  it('returns null when there is no assistant message', () => {
    expect(getLastAssistantMessageId([msg('1', 'user')])).toBeNull();
  });

  it('returns null for an empty list', () => {
    expect(getLastAssistantMessageId([])).toBeNull();
  });
});

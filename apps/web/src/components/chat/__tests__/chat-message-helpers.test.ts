/**
 * getLastAssistantMessageId — drives which row animates its psyche emoji (spec D-5).
 */

import { describe, it, expect } from 'vitest';

import { getLastAssistantMessageId, greetingForHour } from '../ChatMessageList';
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

describe('greetingForHour', () => {
  it('rests during deep night (23:00–04:59), flagged isNight', () => {
    for (const h of [23, 0, 2, 4]) {
      expect(greetingForHour(h)).toEqual({ glyph: '😴', isNight: true });
    }
  });

  it('serves coffee in the morning (05:00–10:59)', () => {
    for (const h of [5, 8, 10]) {
      expect(greetingForHour(h)).toEqual({ glyph: '☕', isNight: false });
    }
  });

  it('waves during the day (11:00–17:59)', () => {
    for (const h of [11, 14, 17]) {
      expect(greetingForHour(h)).toEqual({ glyph: '👋', isNight: false });
    }
  });

  it('shows the moon in the evening (18:00–22:59)', () => {
    for (const h of [18, 21, 22]) {
      expect(greetingForHour(h)).toEqual({ glyph: '🌛', isNight: false });
    }
  });

  it('covers every hour with exactly one non-night bucket outside 23–04', () => {
    for (let h = 0; h < 24; h++) {
      const g = greetingForHour(h);
      expect(['😴', '☕', '👋', '🌛']).toContain(g.glyph);
      expect(g.isNight).toBe(h >= 23 || h < 5);
    }
  });
});

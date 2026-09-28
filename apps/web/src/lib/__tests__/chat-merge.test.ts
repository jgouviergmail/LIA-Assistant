/**
 * Merging the newest server page into the thread on screen (ADR-320).
 *
 * The oracle is what a reader would see: nothing that is on screen disappears,
 * moves or remounts; what the server holds and the screen does not appears in
 * its place; a bubble is never shown twice.
 */

import { describe, expect, it } from 'vitest';

import { mergeServerPage } from '@/lib/chat-merge';
import type { Message } from '@/types/chat';

const T0 = Date.parse('2026-09-25T10:00:00Z');

/** A history row: its id IS its archived row, as `toUiMessage` builds it. */
function row(
  id: string,
  minute: number,
  content = `row ${id}`,
  extra: Partial<Message> = {}
): Message {
  return {
    id,
    role: 'assistant',
    content,
    timestamp: new Date(T0 + minute * 60_000),
    metadata: { message_db_id: id },
    ...extra,
  };
}

/** A bubble the live stream created (client id), optionally knowing its row. */
function live(id: string, content: string, role: 'user' | 'assistant', dbId?: string): Message {
  return {
    id,
    role,
    content,
    timestamp: new Date(T0 + 99 * 60_000),
    metadata: dbId ? { message_db_id: dbId } : {},
  };
}

function ids(messages: Message[]): string[] {
  return messages.map(message => message.id);
}

describe('mergeServerPage — what is on screen stays', () => {
  it('returns the SAME array when the page brings nothing new', () => {
    const thread = [row('a', 1), row('b', 2)];
    const page = [row('a', 1), row('b', 2)];

    const merged = mergeServerPage(thread, page);

    expect(merged.messages).toBe(thread);
    expect(merged.gap).toBe(false);
  });

  it('appends what arrived and keeps every existing bubble as the same object', () => {
    const thread = [row('a', 1), row('b', 2)];
    const page = [row('a', 1), row('b', 2), row('c', 3)];

    const merged = mergeServerPage(thread, page).messages;

    expect(ids(merged)).toEqual(['a', 'b', 'c']);
    expect(merged[0]).toBe(thread[0]);
    expect(merged[1]).toBe(thread[1]);
  });

  it('keeps the older pages the reader scrolled into', () => {
    const thread = [row('old1', 1), row('old2', 2), row('p1', 3), row('p2', 4)];
    const page = [row('p1', 3), row('p2', 4), row('new', 5)];

    const merged = mergeServerPage(thread, page).messages;

    expect(ids(merged)).toEqual(['old1', 'old2', 'p1', 'p2', 'new']);
    expect(merged[0]).toBe(thread[0]);
  });

  it('never empties the thread on an empty page — a failed read looks the same', () => {
    const thread = [row('a', 1)];

    expect(mergeServerPage(thread, []).messages).toBe(thread);
  });
});

describe('mergeServerPage — a live turn is recognised as the rows it became', () => {
  it('matches the question and the answer by the ids their done chunk gave them', () => {
    const question = live('client-u', 'Quelle heure ?', 'user', 'u1');
    const answer = live('client-a', 'Il est midi.', 'assistant', 'a1');
    const thread = [row('a', 1), question, answer];
    const page = [
      row('a', 1),
      { ...row('u1', 2, 'Quelle heure ?'), role: 'user' as const },
      row('a1', 3, 'Il est midi.'),
    ];

    const merged = mergeServerPage(thread, page).messages;

    expect(merged).toBe(thread);
  });

  it('pairs a question no id names by its words, and teaches it its row', () => {
    // An interrupted turn ends without a done chunk: the bubble never learned
    // its row, and must not be shown a second time beside it.
    const question = live('client-u', 'Envoie  le mail\n', 'user');
    const thread = [row('a', 1), question];
    const page = [row('a', 1), { ...row('u1', 2, 'Envoie le mail'), role: 'user' as const }];

    const merged = mergeServerPage(thread, page).messages;

    expect(ids(merged)).toEqual(['a', 'client-u']);
    expect(merged[1].metadata?.message_db_id).toBe('u1');
  });

  it('pairs the HITL question streamed token by token with the row archived after it', () => {
    const asked = live('hitl_1', 'Confirmes-tu  l’envoi ? ', 'assistant');
    const thread = [row('u0', 1), asked];
    const page = [row('u0', 1), row('q1', 2, 'Confirmes-tu l’envoi ?')];

    const merged = mergeServerPage(thread, page).messages;

    expect(ids(merged)).toEqual(['u0', 'hitl_1']);
  });

  it('never pairs two archived rows by their words — two rows with the same text are two rows', () => {
    const thread = [row('ok1', 1, 'ok'), row('ok2', 2, 'ok')];
    const page = [row('ok1', 1, 'ok'), row('ok2', 2, 'ok'), row('ok3', 3, 'ok')];

    expect(ids(mergeServerPage(thread, page).messages)).toEqual(['ok1', 'ok2', 'ok3']);
  });

  it('matches a live-session row by the server id it was appended under', () => {
    const spoken: Message = {
      id: 'lt1',
      role: 'user',
      content: 'Bonjour',
      timestamp: new Date(T0 + 2 * 60_000),
      metadata: { type: 'live_turn' },
    };
    const thread = [row('a', 1), spoken];
    const page = [row('a', 1), { ...row('lt1', 2, 'Bonjour'), role: 'user' as const }];

    const merged = mergeServerPage(thread, page).messages;

    // Adopted from the server under the SAME id: a re-render, not a remount.
    expect(ids(merged)).toEqual(['a', 'lt1']);
  });
});

describe('mergeServerPage — what only this tab holds stays in place', () => {
  it('keeps an error bubble right after the bubble it followed', () => {
    const question = live('client-u', 'Hello', 'user', 'u1');
    const error: Message = { ...live('err', 'Oops', 'assistant'), metadata: { type: 'error' } };
    const thread = [row('a', 1), question, error];
    const page = [row('a', 1), { ...row('u1', 2, 'Hello'), role: 'user' as const }, row('n', 3)];

    expect(ids(mergeServerPage(thread, page).messages)).toEqual(['a', 'client-u', 'err', 'n']);
  });

  it('places a row archived meanwhile before the live answer that followed it on the server', () => {
    // A reminder landed while the turn streamed: the server orders it first.
    const question = live('client-u', 'Hi', 'user', 'u1');
    const answer = live('client-a', 'Hello!', 'assistant', 'a1');
    const thread = [row('a', 1), question, answer];
    const page = [
      row('a', 1),
      { ...row('u1', 2, 'Hi'), role: 'user' as const },
      row('reminder', 3, 'Rappel'),
      row('a1', 4, 'Hello!'),
    ];

    const merged = mergeServerPage(thread, page).messages;

    expect(ids(merged)).toEqual(['a', 'client-u', 'reminder', 'client-a']);
    expect(merged[3]).toBe(answer);
  });

  it('drops a second bubble naming a row another already stands for', () => {
    const thread = [row('a', 1), live('client-a', 'row a', 'assistant', 'a')];
    const page = [row('a', 1)];

    expect(ids(mergeServerPage(thread, page).messages)).toEqual(['a']);
  });
});

describe('mergeServerPage — a row the server changed since', () => {
  it('is taken from the server under the SAME id (a restated card, a late token count)', () => {
    const before = row('a', 1, 'Voici', {
      generatedImages: [{ url: '/api/v1/attachments/x', alt: 'x', expires_at: 'soon' }],
    });
    const after = row('a', 1, 'Voici', { tokensIn: 42 });
    after.metadata = { ...after.metadata, generated_images: [{ kept: true }] };

    const merged = mergeServerPage([before], [after]).messages;

    expect(merged[0]).toBe(after);
    expect(merged[0].id).toBe('a');
  });
});

describe('mergeServerPage — more than a page arrived while away', () => {
  it('replaces the thread with the page and says so, keeping the live bubbles', () => {
    const pending = live('client-u', 'Still here?', 'user');
    const thread = [row('old1', 1), row('old2', 2), pending];
    const page = [row('n1', 10), row('n2', 11)];

    const merged = mergeServerPage(thread, page);

    expect(merged.gap).toBe(true);
    expect(ids(merged.messages)).toEqual(['n1', 'n2', 'client-u']);
  });

  it('ignores a page older than everything on screen — a stale read adds nothing', () => {
    const thread = [row('a', 10), row('b', 11)];
    const page = [row('x', 1), row('y', 2)];

    const merged = mergeServerPage(thread, page);

    expect(merged.messages).toBe(thread);
    expect(merged.gap).toBe(false);
  });

  it('fills an empty thread with the page, without calling it a gap', () => {
    const merged = mergeServerPage([], [row('a', 1)]);

    expect(ids(merged.messages)).toEqual(['a']);
    expect(merged.gap).toBe(false);
  });
});

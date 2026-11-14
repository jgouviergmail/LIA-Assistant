/**
 * What the composer does with words written while LIA works (ADR-384), and how a
 * waiting message joins the answer being written (ADR-385).
 */
import { describe, expect, it } from 'vitest';

import {
  composerRoute,
  isQueueable,
  streamIdOf,
  waitingActions,
  waitingLineKey,
  type WaitingMessage,
} from '@/lib/waiting-message';

function waiting(overrides: Partial<WaitingMessage> = {}): WaitingMessage {
  return {
    conversation_id: 'c1',
    conversation_revision: 0,
    content: 'And the bakery',
    status: 'waiting',
    version: 1,
    send_requested: false,
    stream_id: null,
    can_join: false,
    created_at: '2026-11-13T15:00:00Z',
    updated_at: '2026-11-13T15:00:00Z',
    ...overrides,
  };
}

describe('isQueueable', () => {
  it('lets plain typed text wait', () => {
    expect(isQueueable({})).toBe(true);
    expect(isQueueable({ attachmentIds: [] })).toBe(true);
  });

  it.each([
    ['attachments', { attachmentIds: ['a'] }],
    ['a dictation cost', { sttProvider: 'elevenlabs' }],
    ['a one-click decision', { hitlDecision: true }],
    ['a capability directive', { directive: true }],
    ['a live session', { live: true }],
    ['a card composition', { composition: true }],
  ])('keeps the live request for %s', (_label, send) => {
    expect(isQueueable(send)).toBe(false);
  });
});

describe('composerRoute', () => {
  const base = { busy: false, waiting: false, questionPending: false, queueable: true };

  it('sends a plain message on a free account with nothing waiting', () => {
    expect(composerRoute(base)).toBe('send');
  });

  it('queues while LIA works', () => {
    expect(composerRoute({ ...base, busy: true })).toBe('queue');
  });

  it('adds to what waits when the account is free', () => {
    expect(composerRoute({ ...base, waiting: true })).toBe('queue');
  });

  it('answers a pending question instead of adding to what waits', () => {
    expect(composerRoute({ ...base, waiting: true, questionPending: true })).toBe('send');
  });

  it('never queues what only the live request can carry', () => {
    expect(composerRoute({ ...base, busy: true, queueable: false })).toBe('send');
  });
});

describe('waitingLineKey', () => {
  it.each([
    [waiting(), false, 'chat.waiting.line_waiting'],
    [waiting(), true, 'chat.waiting.line_after_question'],
    [waiting({ send_requested: true }), false, 'chat.waiting.line_send_requested'],
    [waiting({ status: 'held' }), false, 'chat.waiting.line_held'],
    [waiting({ status: 'held' }), true, 'chat.waiting.line_after_question'],
    [waiting({ status: 'departing', stream_id: 's' }), false, 'chat.waiting.line_departing'],
    [waiting({ status: 'joining', stream_id: 's' }), false, 'chat.waiting.line_joining'],
  ])('names the state of %o (question pending: %s)', (message, question, key) => {
    expect(waitingLineKey(message, question)).toBe(key);
  });
});

describe('waitingActions', () => {
  it('offers edit, withdraw and send now while it waits', () => {
    expect(waitingActions(waiting(), false)).toEqual({
      edit: true,
      withdraw: true,
      sendNow: true,
      join: false,
    });
  });

  it('never offers to send it as the answer to a pending question', () => {
    expect(waitingActions(waiting(), true)).toEqual({
      edit: true,
      withdraw: true,
      sendNow: false,
      join: false,
    });
  });

  it('offers to join the answer only while that answer takes notes', () => {
    expect(waitingActions(waiting({ can_join: true }), false).join).toBe(true);
    expect(waitingActions(waiting({ can_join: true, status: 'held' }), false).join).toBe(true);
    expect(waitingActions(waiting({ can_join: false }), false).join).toBe(false);
  });

  it('never offers to join while a question waits for its answer', () => {
    expect(waitingActions(waiting({ can_join: true }), true).join).toBe(false);
  });

  it('lets a joining note be changed or withdrawn until LIA reads it, nothing else', () => {
    expect(waitingActions(waiting({ status: 'joining', stream_id: 's' }), false)).toEqual({
      edit: true,
      withdraw: true,
      sendNow: false,
      join: false,
    });
  });

  it('offers send now once only', () => {
    expect(waitingActions(waiting({ send_requested: true }), false).sendNow).toBe(false);
  });

  it('offers nothing while it is being sent', () => {
    expect(
      waitingActions(waiting({ status: 'departing', stream_id: 's', can_join: true }), false)
    ).toEqual({
      edit: false,
      withdraw: false,
      sendNow: false,
      join: false,
    });
  });
});

describe('streamIdOf', () => {
  it('reads the run a chunk belongs to', () => {
    expect(streamIdOf({ stream_id: 'abc' })).toBe('abc');
  });

  it('ignores a chunk without one', () => {
    expect(streamIdOf(undefined)).toBeNull();
    expect(streamIdOf({ stream_id: 7 })).toBeNull();
    expect(streamIdOf({ stream_id: '' })).toBeNull();
  });
});

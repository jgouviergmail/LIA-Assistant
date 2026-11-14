/**
 * useMailReplyMarks — where the rows of a mail listing stand in their conversations,
 * read APART (ADR-369, ADR-379).
 *
 * The listing is one search and never waits. Its rows are asked a page at a time once
 * they are on screen; page one read again is asked again, so a reply sent since shows;
 * a next page asks its own rows; a row changed on screen asks nothing. A mailbox that
 * cannot tell marks nothing and costs the list nothing.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderHook, waitFor } from '@/__tests__/test-utils';
import type { MailReplyMark, MailSummary } from '@/lib/workbench/types';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));

import { useMailReplyMarks } from '../useMailReplyMarks';

function row(id: string, overrides: Partial<MailSummary> = {}): MailSummary {
  return {
    id,
    thread_id: `t-${id}`,
    sender: null,
    subject: `Subject ${id}`,
    snippet: '',
    received_at: null,
    is_read: true,
    is_starred: false,
    has_attachments: false,
    label_ids: [],
    ...overrides,
  };
}

function rows(...ids: string[]): MailSummary[] {
  return ids.map(id => row(id));
}

function marks(...items: [string, MailReplyMark][]) {
  return { items: items.map(([id, status]) => ({ id, status })) };
}

/** The rows a call asked for. */
function asked(call: number): string[] {
  const body = post.mock.calls[call]?.[1] as { messages: { id: string }[] };
  return body.messages.map(message => message.id);
}

/** The signal a call travelled under. */
function signalOf(call: number): AbortSignal {
  return (post.mock.calls[call]?.[2] as { signal: AbortSignal }).signal;
}

/** A POST the test answers by hand. */
function deferred<T>(): { promise: Promise<T>; answer: (value: T) => void } {
  let answer!: (value: T) => void;
  const promise = new Promise<T>(resolve => {
    answer = resolve;
  });
  return { promise, answer };
}

interface Listing {
  enabled?: boolean;
  read: number;
  rows: MailSummary[];
  pageSize?: number;
}

function marksOf(initial: Listing) {
  return renderHook(
    ({ enabled = true, read, rows: shown, pageSize = 25 }: Listing) =>
      useMailReplyMarks(enabled, read, shown, pageSize),
    { initialProps: initial }
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  post.mockResolvedValue(marks());
});

describe('useMailReplyMarks', () => {
  it('asks the marks of the page shown and gives each row its own', async () => {
    post.mockResolvedValue(marks(['m1', 'answered']));
    const { result } = marksOf({ read: 1, rows: rows('m1', 'm2') });

    await waitFor(() => expect(result.current(row('m1'))).toBe('answered'));
    expect(result.current(row('m2'))).toBeUndefined();
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith(
      '/workbench/mail/reply-marks',
      {
        messages: [
          { id: 'm1', thread_id: 't-m1' },
          { id: 'm2', thread_id: 't-m2' },
        ],
      },
      { signal: expect.any(AbortSignal) }
    );
  });

  it('asks a next page its own rows only, and keeps the marks already read', async () => {
    post.mockResolvedValueOnce(marks(['m1', 'answered']));
    const { result, rerender } = marksOf({ read: 1, rows: rows('m1', 'm2') });
    await waitFor(() => expect(result.current(row('m1'))).toBe('answered'));
    post.mockResolvedValueOnce(marks(['m3', 'reply_received']));

    rerender({ read: 1, rows: rows('m1', 'm2', 'm3') });

    await waitFor(() => expect(result.current(row('m3'))).toBe('reply_received'));
    expect(asked(1)).toEqual(['m3']);
    expect(result.current(row('m1'))).toBe('answered');
  });

  it('asks nothing when a row only changes on screen', async () => {
    post.mockResolvedValue(marks(['m1', 'answered']));
    const { result, rerender } = marksOf({ read: 1, rows: rows('m1', 'm2') });
    await waitFor(() => expect(result.current(row('m1'))).toBe('answered'));

    // A star shown at once: the same read of the page, the same rows, new objects.
    rerender({ read: 1, rows: [row('m1', { is_starred: true }), row('m2')] });

    expect(result.current(row('m1'))).toBe('answered');
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('asks again when page one is read again, and a mark that no longer holds leaves', async () => {
    post.mockResolvedValueOnce(marks(['m1', 'answer_drafted']));
    const { result, rerender } = marksOf({ read: 1, rows: rows('m1') });
    await waitFor(() => expect(result.current(row('m1'))).toBe('answer_drafted'));
    const again = deferred<ReturnType<typeof marks>>();
    post.mockReturnValueOnce(again.promise);

    rerender({ read: 2, rows: rows('m1') });

    // What is on screen stays until the answer lands.
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(result.current(row('m1'))).toBe('answer_drafted');
    again.answer(marks());
    await waitFor(() => expect(result.current(row('m1'))).toBeUndefined());
  });

  it('never cuts short an answer on its way because a next page came', async () => {
    // The mailbox already paid its reads for that answer: it is waited for, not asked twice.
    const first = deferred<ReturnType<typeof marks>>();
    post.mockReturnValueOnce(first.promise);
    const { result, rerender } = marksOf({ read: 1, rows: rows('m1', 'm2') });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));

    rerender({ read: 1, rows: rows('m1', 'm2', 'm3') });

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(asked(1)).toEqual(['m3']);
    expect(signalOf(0).aborted).toBe(false);
    first.answer(marks(['m1', 'answered']));
    await waitFor(() => expect(result.current(row('m1'))).toBe('answered'));
  });

  it('cuts short what the previous read of the page still had on its way', async () => {
    const late = deferred<ReturnType<typeof marks>>();
    post.mockReturnValueOnce(late.promise);
    const { result, rerender } = marksOf({ read: 1, rows: rows('m1') });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));

    rerender({ read: 2, rows: rows('m1') });

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(signalOf(0).aborted).toBe(true);
    // A late answer to the read that is gone marks nothing.
    await act(async () => {
      late.answer(marks(['m1', 'answered']));
      await late.promise;
    });
    expect(result.current(row('m1'))).toBeUndefined();
  });

  it('marks nothing when the mailbox cannot tell, and does not ask again', async () => {
    post.mockRejectedValue(new Error('away'));
    const { result, rerender } = marksOf({ read: 1, rows: rows('m1') });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));

    rerender({ read: 1, rows: [row('m1', { is_read: false })] });

    expect(result.current(row('m1'))).toBeUndefined();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('reads nothing into an answer of another shape', async () => {
    post.mockResolvedValue({ done: ['m1'], failed: [] });
    const { result } = marksOf({ read: 1, rows: rows('m1') });

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(result.current(row('m1'))).toBeUndefined();
  });

  it('asks a long listing a page at a time', async () => {
    marksOf({ read: 1, rows: rows('m1', 'm2', 'm3', 'm4', 'm5'), pageSize: 2 });

    await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
    expect([asked(0), asked(1), asked(2)]).toEqual([['m1', 'm2'], ['m3', 'm4'], ['m5']]);
  });

  it('asks nothing where no mark is offered, and shows none', async () => {
    post.mockResolvedValue(marks(['m1', 'answered']));
    const { result, rerender } = marksOf({ read: 1, rows: rows('m1') });
    await waitFor(() => expect(result.current(row('m1'))).toBe('answered'));

    // The trash, say: other rows, and the one already marked among them.
    rerender({ enabled: false, read: 2, rows: rows('m1', 'm9') });

    expect(result.current(row('m1'))).toBeUndefined();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('asks nothing before a page is on screen', () => {
    marksOf({ read: 0, rows: [] });

    expect(post).not.toHaveBeenCalled();
  });
});

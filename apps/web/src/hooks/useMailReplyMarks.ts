'use client';

/**
 * Where the rows of a mail listing stand in their conversations (ADR-369, ADR-379),
 * read APART from the listing.
 *
 * A listing is one search and never waits. Once a page is on screen its rows are asked —
 * a page at a time, the published page size — and each answer marks the rows something
 * happened to: answered, an answer drafted, a reply received. Page one read again (a
 * refresh, another folder) is asked again, so a reply sent since then shows; what is on
 * screen stays until that answer lands, and what the previous read still had on its way
 * is cut short. A next page asks its own rows only and cuts nothing: an answer on its
 * way has already cost the mailbox its reads. A row changed on screen (a star, a read
 * state) asks nothing. A read that fails marks nothing and is not asked again before the
 * page is: the marks never cost the list anything.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import apiClient from '@/lib/api-client';
import type { MailReplyMark, MailReplyMarks, MailSummary } from '@/lib/workbench/types';

const REPLY_MARKS = '/workbench/mail/reply-marks';

/** The marks read so far, and the read of page one they belong to. */
interface Shown {
  read: number;
  marks: ReadonlyMap<string, MailReplyMark>;
}

/** What one read of page one asks: cut short when the page is read again. */
interface Session {
  read: number;
  transport: AbortController;
  /** The rows already asked: each is asked once per read of the page. */
  asked: Set<string>;
}

const NOTHING: Shown = { read: 0, marks: new Map() };

/** `shown` after a request answered: the rows something happened to take their mark. */
function answered(shown: Shown, read: number, items: MailReplyMarks['items']): Shown {
  // Marks of an earlier read of the page are let go with its first answer, never before:
  // a mark that no longer holds leaves then.
  const marks = new Map(shown.read === read ? shown.marks : undefined);
  for (const item of items) marks.set(item.id, item.status);
  return { read, marks };
}

/**
 * @param enabled - Whether the mailbox offers the marks here (`reply_marks`, a folder
 *   where an answer makes sense).
 * @param read - Which read of page one the rows come from (`useWorkbenchPage`); zero
 *   while nothing is shown.
 * @param rows - The rows on screen.
 * @param pageSize - How many rows one request may name (the published page size).
 * @returns Each row's mark, when something happened to it.
 */
export function useMailReplyMarks(
  enabled: boolean,
  read: number,
  rows: readonly MailSummary[],
  pageSize: number
): (message: MailSummary) => MailReplyMark | undefined {
  const [shown, setShown] = useState<Shown>(NOTHING);
  // Bumped when a request settles: the rows still unasked are asked next.
  const [round, setRound] = useState(0);
  const session = useRef<Session | null>(null);
  // The rows as a request names them: a row changed on screen keeps its key.
  const rowsKey = JSON.stringify(rows.map(row => [row.id, row.thread_id]));

  // One session per read of page one, opened before the rows below are asked.
  useEffect(() => {
    if (!enabled) return;
    const opened: Session = { read, transport: new AbortController(), asked: new Set() };
    session.current = opened;
    return () => {
      opened.transport.abort();
      if (session.current === opened) session.current = null;
    };
  }, [enabled, read]);

  // Runs after the session above opens or closes (`enabled`, `read`), a page lands
  // (`rowsKey`) or a request settles (`round`): the rows not asked yet, a page at a time.
  useEffect(() => {
    const current = session.current;
    if (current === null) return;
    const refs = (JSON.parse(rowsKey) as [string, string][])
      .filter(([id]) => !current.asked.has(id))
      .slice(0, pageSize);
    if (refs.length === 0) return;
    for (const [id] of refs) current.asked.add(id);
    const { signal } = current.transport;
    apiClient
      .post<MailReplyMarks>(
        REPLY_MARKS,
        { messages: refs.map(([id, thread_id]) => ({ id, thread_id })) },
        { signal }
      )
      .then(answer => {
        if (signal.aborted) return;
        // An answer of another shape marks nothing: the page never depends on its marks.
        const items = Array.isArray(answer?.items) ? answer.items : [];
        setShown(held => answered(held, current.read, items));
      })
      // Fail-open: a mailbox that cannot tell marks nothing.
      .catch(() => undefined)
      .finally(() => setRound(count => count + 1));
  }, [enabled, read, rowsKey, pageSize, round]);

  return useCallback(
    (message: MailSummary) => (enabled ? shown.marks.get(message.id) : undefined),
    [enabled, shown]
  );
}

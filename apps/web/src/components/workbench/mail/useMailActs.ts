'use client';

/**
 * The mail screen's acts, as the person sees them (ADR-369, Task 4.7).
 *
 * Every act on several messages is told as it went — all done, some done (the
 * others stay listed), none done — and a refusal of the whole act in the
 * refusal's own words. The open message's acts change the reader AND its row
 * at once, and roll both back when the provider refuses. Opening an unread
 * message marks it read after a short look (`MAIL_READ_DWELL_MS`, the
 * mock-ups' reader offers « Mark as unread »): a message opened by mistake and
 * closed at once stays unread, and a failure of that mark is said by the row
 * staying bold — the person did not ask for it, so no toast.
 *
 * A message sent somewhere comes back by the toast's « Undo »: what the act
 * answered names it (Graph and IMAP give it another id), and the listing is where
 * it returns. A listing that is a view has no place to return to, and a message
 * whose new id the provider did not say cannot be named: neither offers the way
 * back. The trash has its « Restore », whichever way a message got there.
 */
import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import type { WorkbenchMailState } from '@/hooks/useWorkbenchMail';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { actReport, isPlace, SEND_PLACES, type MailSendAct } from '@/lib/workbench/mail';
import type {
  MailMessage,
  MailMoveOutcome,
  MailSummary,
  WorkbenchActOutcome,
} from '@/lib/workbench/types';

import type { MailBulkAct } from './MailSelectionBar';
import type { ReaderAct } from './MessageReader';

/** How long the way back stays on screen. */
const UNDO_TOAST_MS = 8000;

/** What each act says it did. */
const SENT_KEYS: Readonly<Record<MailSendAct, string>> = {
  trash: 'workbench.mail.trashed',
  archive: 'workbench.mail.archived',
  spam: 'workbench.mail.reported_spam',
  not_spam: 'workbench.mail.not_spam_done',
  restore: 'workbench.mail.restored',
  move: 'workbench.mail.moved',
};

/** The open message as a row, for an act that changes both. */
function asRow(message: MailMessage, rows: readonly MailSummary[]): MailSummary {
  return (
    rows.find(row => row.id === message.id) ?? {
      ...message,
      snippet: '',
      has_attachments: message.attachments.length > 0,
    }
  );
}

export interface MailActs {
  bulkBusy: MailBulkAct | null;
  readerBusy: ReaderAct | null;
  /** Says why an act was refused, in the refusal's own words. */
  tell: (error: unknown) => void;
  readSelection: (rows: readonly MailSummary[], read: boolean) => Promise<void>;
  starSelection: (rows: readonly MailSummary[], starred: boolean) => Promise<void>;
  /**
   * Sends messages somewhere, and offers the way back.
   *
   * @param to - The folder of a `move`; the other acts know their place.
   * @returns The messages moved (the selection keeps the others).
   */
  send: (ids: readonly string[], act: MailSendAct, to?: string) => Promise<readonly string[]>;
  /** @returns The messages deleted (the selection keeps the others). */
  deleteForever: (ids: readonly string[]) => Promise<readonly string[]>;
  emptyTrash: () => Promise<void>;
  labelSelection: (rows: readonly MailSummary[], add: string[], remove: string[]) => Promise<void>;
  setOpenRead: (read: boolean, quiet?: boolean) => Promise<void>;
  setOpenStarred: (starred: boolean) => Promise<void>;
  labelOpen: (add: string[], remove: string[]) => Promise<void>;
}

/**
 * @param lng - The reader's language.
 * @param mail - The screen's reads and acts.
 * @param open - The open message.
 * @param folder - The listing: where a message sent away comes back to.
 * @param onUnread - What changed in the listing's unread figure, by how much.
 * @param onSent - A message left a folder: the figures are read again.
 */
export function useMailActs(
  lng: Language,
  mail: WorkbenchMailState,
  open: WorkbenchItemState<MailMessage>,
  folder: string,
  onUnread: (delta: number) => void,
  onSent: () => void
): MailActs {
  const { t } = useTranslation(lng);
  const [bulkBusy, setBulkBusy] = useState<MailBulkAct | null>(null);
  const [readerBusy, setReaderBusy] = useState<ReaderAct | null>(null);
  const rows = mail.messages.items;
  const { setItem } = open;

  const tell = useCallback(
    (error: unknown) => {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.mail.act_failed'));
    },
    [t]
  );

  /** Tells an act that did not do everything; a full success is shown by the list itself. */
  const report = useCallback(
    (outcome: WorkbenchActOutcome, doneKey?: string, undo?: () => void) => {
      const { tone, done, failed } = actReport(outcome);
      if (tone === 'success') {
        const way = undo && {
          action: { label: t('workbench.mail.undo'), onClick: undo },
          duration: UNDO_TOAST_MS,
        };
        if (doneKey) toast.success(t(doneKey, { count: done }), way);
      } else if (tone === 'partial') {
        toast.error(t('workbench.mail.partial', { done, failed }));
      } else {
        toast.error(t('workbench.mail.none_done', { count: failed }));
      }
    },
    [t]
  );

  const bulk = useCallback(
    async <T>(act: MailBulkAct, run: () => Promise<T>): Promise<T | undefined> => {
      setBulkBusy(act);
      try {
        return await run();
      } catch (error: unknown) {
        tell(error);
        return undefined;
      } finally {
        setBulkBusy(null);
      }
    },
    [tell]
  );

  const readSelection = useCallback(
    async (selected: readonly MailSummary[], read: boolean) => {
      const outcome = await bulk(read ? 'read' : 'unread', () => mail.setRead(selected, read));
      if (!outcome) return;
      report(outcome);
      const changed = selected.filter(
        row => row.is_read !== read && outcome.done.includes(row.id)
      ).length;
      if (changed > 0) onUnread(read ? -changed : changed);
    },
    [bulk, mail, onUnread, report]
  );

  const starSelection = useCallback(
    async (selected: readonly MailSummary[], starred: boolean) => {
      const outcome = await bulk('star', () => mail.setStarred(selected, starred));
      if (outcome) report(outcome);
    },
    [bulk, mail, report]
  );

  const undo = useCallback(
    async (ids: readonly string[], from: string) => {
      try {
        report(await mail.move(ids, folder, from), 'workbench.mail.undone');
        await mail.messages.refresh();
        onSent();
      } catch (error: unknown) {
        tell(error);
      }
    },
    [folder, mail, onSent, report, tell]
  );

  const send = useCallback(
    async (ids: readonly string[], act: MailSendAct, to?: string) => {
      const place = act === 'move' ? to : SEND_PLACES[act];
      if (!place) return [];
      const outcome: MailMoveOutcome | undefined = await bulk(act, () => mail.move(ids, place));
      if (!outcome) return [];
      const named = outcome.moved.flatMap(item => (item.new_id ? [item.new_id] : []));
      const back = isPlace(folder) && named.length === outcome.done.length && named.length > 0;
      report(outcome, SENT_KEYS[act], back ? () => void undo(named, place) : undefined);
      onSent();
      return outcome.done;
    },
    [bulk, folder, mail, onSent, report, undo]
  );

  const deleteForever = useCallback(
    async (ids: readonly string[]) => {
      const outcome = await bulk('forever', () => mail.deleteForever(ids));
      if (!outcome) return [];
      report(outcome, 'workbench.mail.deleted_forever');
      return outcome.done;
    },
    [bulk, mail, report]
  );

  const emptyTrash = useCallback(async () => {
    const emptied = await bulk('empty', () => mail.emptyTrash());
    if (!emptied) return;
    toast.success(
      t(emptied.remaining ? 'workbench.mail.emptied_more' : 'workbench.mail.emptied', {
        count: emptied.deleted,
      })
    );
  }, [bulk, mail, t]);

  const labelSelection = useCallback(
    async (selected: readonly MailSummary[], add: string[], remove: string[]) => {
      await bulk('labels', () => mail.applyLabels(selected, add, remove));
    },
    [bulk, mail]
  );

  const setOpenRead = useCallback(
    async (read: boolean, quiet = false) => {
      const message = open.item;
      if (!message || message.is_read === read) return;
      if (!quiet) setReaderBusy('read');
      setItem(current => ({ ...current, is_read: read }));
      try {
        const outcome = await mail.setRead([asRow(message, rows)], read);
        // Not done — refused, or never asked because its previous act was on its way.
        if (!outcome.done.includes(message.id)) {
          setItem(current => ({ ...current, is_read: !read }));
          if (!quiet && outcome.failed.length > 0) report(outcome);
        } else if (rows.some(row => row.id === message.id)) {
          onUnread(read ? -1 : 1);
        } else {
          // Opened from its conversation, it may live elsewhere: the server knows which figure.
          onSent();
        }
      } catch (error: unknown) {
        setItem(current => ({ ...current, is_read: !read }));
        if (!quiet) tell(error);
      } finally {
        if (!quiet) setReaderBusy(null);
      }
    },
    [mail, onSent, onUnread, open.item, report, rows, setItem, tell]
  );

  const setOpenStarred = useCallback(
    async (starred: boolean) => {
      const message = open.item;
      if (!message || message.is_starred === starred) return;
      setReaderBusy('star');
      setItem(current => ({ ...current, is_starred: starred }));
      try {
        const outcome = await mail.setStarred([asRow(message, rows)], starred);
        if (!outcome.done.includes(message.id)) {
          setItem(current => ({ ...current, is_starred: !starred }));
          if (outcome.failed.length > 0) report(outcome);
        }
      } catch (error: unknown) {
        setItem(current => ({ ...current, is_starred: !starred }));
        tell(error);
      } finally {
        setReaderBusy(null);
      }
    },
    [mail, open.item, report, rows, setItem, tell]
  );

  const labelOpen = useCallback(
    async (add: string[], remove: string[]) => {
      const message = open.item;
      if (!message) return;
      setReaderBusy('labels');
      try {
        await mail.applyLabels([asRow(message, rows)], add, remove);
        setItem(current => ({
          ...current,
          label_ids: [
            ...current.label_ids.filter(id => !remove.includes(id)),
            ...add.filter(id => !current.label_ids.includes(id)),
          ],
        }));
      } catch (error: unknown) {
        tell(error);
      } finally {
        setReaderBusy(null);
      }
    },
    [mail, open.item, rows, setItem, tell]
  );

  return {
    bulkBusy,
    readerBusy,
    tell,
    readSelection,
    starSelection,
    send,
    deleteForever,
    emptyTrash,
    labelSelection,
    setOpenRead,
    setOpenStarred,
    labelOpen,
  };
}

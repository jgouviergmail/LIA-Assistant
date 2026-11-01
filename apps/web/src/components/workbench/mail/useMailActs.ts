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
 */
import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import type { WorkbenchMailState } from '@/hooks/useWorkbenchMail';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { actReport } from '@/lib/workbench/mail';
import type { WorkbenchActOutcome, MailMessage, MailSummary } from '@/lib/workbench/types';

import type { MailBulkAct } from './MailSelectionBar';
import type { ReaderAct } from './MessageReader';

/** The open message as a row, for an act that changes both. */
function asRow(message: MailMessage, rows: readonly MailSummary[]): MailSummary {
  return rows.find(row => row.id === message.id) ?? { ...message, snippet: '' };
}

export interface MailActs {
  bulkBusy: MailBulkAct | null;
  readerBusy: ReaderAct | null;
  /** Says why an act was refused, in the refusal's own words. */
  tell: (error: unknown) => void;
  readSelection: (rows: readonly MailSummary[], read: boolean) => Promise<void>;
  /** @returns The messages moved (the selection keeps the others). */
  trashSelection: (ids: readonly string[]) => Promise<readonly string[]>;
  labelSelection: (rows: readonly MailSummary[], add: string[], remove: string[]) => Promise<void>;
  setOpenRead: (read: boolean, quiet?: boolean) => Promise<void>;
  /** @returns Whether the open message went to the trash. */
  trashOpen: () => Promise<boolean>;
  labelOpen: (add: string[], remove: string[]) => Promise<void>;
}

export function useMailActs(
  lng: Language,
  mail: WorkbenchMailState,
  open: WorkbenchItemState<MailMessage>
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
    (outcome: WorkbenchActOutcome, doneKey?: string) => {
      const { tone, done, failed } = actReport(outcome);
      if (tone === 'success') {
        if (doneKey) toast.success(t(doneKey, { count: done }));
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
      if (outcome) report(outcome);
    },
    [bulk, mail, report]
  );

  const trashSelection = useCallback(
    async (ids: readonly string[]) => {
      const outcome = await bulk('trash', () => mail.trash(ids));
      if (!outcome) return [];
      report(outcome, 'workbench.mail.trashed');
      return outcome.done;
    },
    [bulk, mail, report]
  );

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
        }
      } catch (error: unknown) {
        setItem(current => ({ ...current, is_read: !read }));
        if (!quiet) tell(error);
      } finally {
        if (!quiet) setReaderBusy(null);
      }
    },
    [mail, open.item, report, rows, setItem, tell]
  );

  const trashOpen = useCallback(async () => {
    const message = open.item;
    if (!message) return false;
    setReaderBusy('trash');
    try {
      const outcome = await mail.trash([message.id]);
      report(outcome, 'workbench.mail.trashed');
      return outcome.done.includes(message.id);
    } catch (error: unknown) {
      tell(error);
      return false;
    } finally {
      setReaderBusy(null);
    }
  }, [mail, open.item, report, tell]);

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
    trashSelection,
    labelSelection,
    setOpenRead,
    trashOpen,
    labelOpen,
  };
}

'use client';

/**
 * The direct acts of the home's cards (owner, 2026-11-07).
 *
 * Each calls the route a click in its tool would call — the person's own act, no model, no
 * register row (ADR-369, D5) — and a reminder is the reminders' own route, through the Tools'
 * dialog. An act that takes the item off the card reads the card again; one the provider refused
 * is said, and the card stays as it was. One act at a time per card: a second press lands before
 * the render that marks the first busy.
 */
import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { ReminderDialog } from '@/components/workbench/assist/ReminderDialog';
import type { Language } from '@/i18n/settings';
import apiClient from '@/lib/api-client';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { MAIL_ARCHIVE, MAIL_INBOX } from '@/lib/workbench/mail';
import type { WorkbenchActOutcome } from '@/lib/workbench/types';

import { useHomeTools } from '../HomeTools';

/** A provider that answered without doing the act on this item. */
class NotDone extends Error {}

function requireDone(outcome: WorkbenchActOutcome | null | undefined, id: string): void {
  if (!outcome?.done.includes(id)) throw new NotDone(id);
}

/** The Tools' routes the cards call, one item at a time. */
export const homeActs = {
  markRead: async (id: string): Promise<void> =>
    requireDone(
      await apiClient.post<WorkbenchActOutcome>('/workbench/mail/read-state', {
        message_ids: [id],
        read: true,
      }),
      id
    ),
  archive: async (id: string): Promise<void> =>
    requireDone(
      await apiClient.post<WorkbenchActOutcome>('/workbench/mail/move', {
        message_ids: [id],
        to: MAIL_ARCHIVE,
        origin: MAIL_INBOX,
      }),
      id
    ),
  complete: async (listId: string, taskId: string): Promise<void> => {
    await apiClient.patch('/workbench/tasks', {
      list_id: listId,
      task_id: taskId,
      completed: true,
    });
  },
  postpone: async (listId: string, taskId: string, due: string): Promise<void> => {
    await apiClient.patch('/workbench/tasks', { list_id: listId, task_id: taskId, due });
  },
};

/**
 * @param onDone - Reads the card again once an act took its item off it.
 * @returns The item whose act runs, how to run one, and the list the card's focus anchors on.
 */
export function useHomeAct(onDone: () => void) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState<string | null>(null);
  const running = useRef(false);
  const list = useRef<HTMLUListElement>(null);

  const run = useCallback(
    async (key: string, act: () => Promise<void>, doneKey: string) => {
      if (running.current) return;
      running.current = true;
      setBusy(key);
      try {
        await act();
        toast.success(t(doneKey));
        // Focus first, while the row still exists: the card's named region outlives every row
        // (the reminders card's rule), and the read that follows removes this one.
        list.current?.closest<HTMLElement>('[role="region"]')?.focus();
        onDone();
      } catch (error: unknown) {
        const refusal = workbenchRefusal(error);
        toast.error(
          refusal ? t(refusal.key, refusal.values) : t('dashboard.briefing.home_acts_failed')
        );
      } finally {
        running.current = false;
        setBusy(null);
      }
    },
    [t, onDone]
  );

  return { busy, run, list };
}

/**
 * « Remind me » from a card: the Tools' own dialog, words filled and theirs to change.
 *
 * @param lng - The page's language.
 * @returns What opens it on some words, and the dialog to render.
 */
export function useHomeReminder(lng: Language) {
  const { zone: accountZone } = useHomeTools();
  const [words, setWords] = useState<string | null>(null);
  const zone = accountZone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  const dialog =
    words === null ? null : (
      <ReminderDialog lng={lng} words={words} zone={zone} onClose={() => setWords(null)} />
    );
  return { remind: setWords, dialog };
}

'use client';

/**
 * Leaving a mailing list from one of its messages (ADR-369, lot 3).
 *
 * The API reads what the message says. One click asks first, then posts by the
 * message's id: the address is read again on the server, never taken from here. A
 * refusal falls back on the sender's page, which the person can open themselves. A
 * list that names only an address gets a message, for the person to read and send.
 */
import { useState, type ReactNode } from 'react';
import { toast } from 'sonner';

import { useConfirm } from '@/components/ui/use-confirm';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { parseMailTo, type ComposerTarget } from '@/lib/workbench/mail-compose';
import type { MailUnsubscribe } from '@/lib/workbench/types';

const WAYS_PATH = '/workbench/mail/message/unsubscribe';
const LEAVE_PATH = '/workbench/mail/unsubscribe';

export interface Leaving {
  /** What the open message says, as far as it still holds. */
  ways: MailUnsubscribe | undefined;
  unsubscribe: () => Promise<void>;
  /** The question, for the screen to draw. */
  confirmDialog: ReactNode;
}

/**
 * @param lng - The reader's language.
 * @param messageId - The open message; null reads nothing.
 * @param compose - Opens the composer on a list's address.
 */
export function useLeaving(
  lng: Language,
  messageId: string | null,
  compose: (target: ComposerTarget) => void
): Leaving {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const read = useWorkbenchItem<MailUnsubscribe>(messageId ? WAYS_PATH : null, {
    id: messageId ?? undefined,
  });
  const { mutate: post } = useApiMutation<{ message_id: string }, void>({
    method: 'POST',
    componentName: 'WorkbenchMail',
  });
  // The one message each answer is about: another one opened starts fresh.
  const [refused, setRefused] = useState<string | null>(null);
  const [left, setLeft] = useState<string | null>(null);
  const said = read.item;
  const ways =
    said && messageId === left
      ? undefined
      : said && messageId === refused
        ? { ...said, one_click: false }
        : said;

  const unsubscribe = async () => {
    if (!ways || !messageId) return;
    if (!ways.one_click) {
      if (ways.mail_to) compose({ kind: 'new', ...parseMailTo(ways.mail_to) });
      return;
    }
    const confirmed = await confirm({
      title: t('workbench.mail.unsubscribe_title'),
      description: t('workbench.mail.unsubscribe_description'),
      confirmLabel: t('workbench.mail.unsubscribe'),
    });
    if (!confirmed) return;
    try {
      await post(LEAVE_PATH, { message_id: messageId });
      setLeft(messageId);
      toast.success(t('workbench.mail.unsubscribed'));
    } catch {
      setRefused(messageId);
      toast.error(t('workbench.mail.unsubscribe_failed'));
    }
  };

  return { ways, unsubscribe, confirmDialog };
}

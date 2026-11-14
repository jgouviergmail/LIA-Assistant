'use client';

/**
 * ReplyMarkIcon — where a message stands in its conversation, as a row's mark (ADR-379).
 *
 * Read alone, a message cannot say whether it was answered: the reply is another message
 * of its conversation. The mark states what HAPPENED — an answer given, an answer drafted
 * and never sent, a reply received to a message sent — and « nothing yet » draws nothing.
 * Like the row's other marks it is never the only carrier: it is an image with a name.
 */
import { MessageSquareReply, PencilLine, Reply } from '@/lib/icons';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { MailReplyMark } from '@/lib/workbench/types';

/** What each mark draws and how it is named. */
const MARKS: Record<MailReplyMark, { icon: typeof Reply; name: string }> = {
  answered: { icon: Reply, name: 'workbench.mail.answered' },
  answer_drafted: { icon: PencilLine, name: 'workbench.mail.answer_drafted' },
  reply_received: { icon: MessageSquareReply, name: 'workbench.mail.reply_received' },
};

export function ReplyMarkIcon({
  lng,
  mark,
  className,
}: {
  lng: Language;
  mark: MailReplyMark;
  className?: string;
}) {
  const { t } = useTranslation(lng);
  const { icon: Icon, name } = MARKS[mark];
  return (
    <Icon
      className={cn('h-4 w-4 shrink-0 text-muted-foreground', className)}
      role="img"
      aria-label={t(name)}
    />
  );
}

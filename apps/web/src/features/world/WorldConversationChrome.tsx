'use client';
import { useId } from 'react';
import { MessageCircle, ShieldCheck, ChevronDown, Megaphone } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { MailboxClientState } from './mailbox-client';
export function ConversationLauncher({
  lng,
  unread,
  disabled,
  onOpen,
}: {
  lng: Language;
  unread: number;
  disabled: boolean;
  onOpen(element: HTMLButtonElement): void;
}) {
  const { t } = useTranslation(lng);
  const unreadId = useId();
  const hasUnread = unread > 0;
  return (
    <Button
      size="sm"
      variant="ghost"
      data-world-conversations
      className="relative min-h-11 min-w-11"
      disabled={disabled}
      aria-label={t('world.messages.action')}
      aria-describedby={hasUnread ? unreadId : undefined}
      onClick={event => {
        onOpen(event.currentTarget);
      }}
    >
      <MessageCircle className="size-4" aria-hidden="true" />
      <span className="hidden sm:inline">{t('world.messages.short')}</span>
      {hasUnread && (
        <>
          <span
            className="world-message-unread rounded-full bg-primary px-1.5 text-xs font-semibold text-primary-foreground"
            aria-hidden="true"
          >
            {unread}
          </span>
          <span id={unreadId} className="sr-only">
            {t('world.messages.unread', { count: unread })}
          </span>
        </>
      )}
    </Button>
  );
}

export function ConversationHeading({
  lng,
  alias,
  mailbox,
  publicMode,
}: {
  lng: Language;
  alias: string;
  mailbox: MailboxClientState['mailbox'];
  publicMode: boolean;
}) {
  const { t } = useTranslation(lng);
  return (
    <DialogHeader className="shrink-0 text-left">
      <DialogTitle className="flex items-center gap-2">
        <MessageCircle className="size-5 text-primary" aria-hidden="true" />
        <span className="truncate">{alias || t('world.messages.title')}</span>
      </DialogTitle>
      <DialogDescription className="sr-only">
        {publicMode
          ? t('world.public.description')
          : t('world.messages.privacy', { minutes: (mailbox?.ttl_seconds ?? 1800) / 60 })}
      </DialogDescription>
      <details className="text-xs text-muted-foreground">
        <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2">
          {publicMode ? (
            <Megaphone className="size-4 shrink-0 text-primary" aria-hidden="true" />
          ) : (
            <ShieldCheck className="size-4 shrink-0 text-primary" aria-hidden="true" />
          )}
          {publicMode
            ? t('world.public.caption')
            : t('world.messages.privacy_short', { minutes: (mailbox?.ttl_seconds ?? 1800) / 60 })}
          <ChevronDown className="ml-auto size-3 shrink-0" aria-hidden="true" />
        </summary>
        <p className="pb-2 leading-relaxed">
          {publicMode
            ? t('world.public.description')
            : t('world.messages.privacy', { minutes: (mailbox?.ttl_seconds ?? 1800) / 60 })}
        </p>
      </details>
    </DialogHeader>
  );
}

'use client';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { PUBLIC_THREAD } from './public-message-protocol';
import type { MailboxClientState } from './mailbox-client';
import type { WorldParticipant } from './useWorldSession';
import type { MessageScrollStore } from './message-scroll-store';
import type { WorldConversation } from './conversation-directory';

/**
 * What both conversation presentations share. It lives apart from the full panel so the
 * always-mounted compact bar never pulls the lazily loaded `WorldMessagePanel` chunk in.
 */
export interface WorldMessagePanelProps {
  lng: Language;
  state: MailboxClientState;
  participants: WorldParticipant[];
  conversations: readonly WorldConversation[];
  tokensVisible: boolean;
  canSend: boolean;
  draft: string;
  recipient: string;
  recipientAlias?: string;
  publicHasDraft?: boolean;
  consent: boolean;
  feedback: boolean;
  scrollStore?: MessageScrollStore;
  onDraft(value: string): void;
  onRecipient(value: string): void;
  onConsent(value: boolean): void;
  onSubmit(): void;
  onTranslate(id: string): void;
  onCheck(): void;
  onDiscard(): void;
  onRetry(): void;
}
export function threadMessages(mailbox: MailboxClientState['mailbox'], recipient: string) {
  if (recipient === PUBLIC_THREAD) return mailbox?.public_messages ?? [];
  return (mailbox?.messages ?? []).filter(
    message => (message.outgoing ? message.recipient_id : message.sender_id) === recipient
  );
}
export function composerEnabled(props: WorldMessagePanelProps): boolean {
  if (!props.canSend || props.state.status !== 'online') return false;
  return props.recipient !== PUBLIC_THREAD || props.state.mailbox?.public_available === true;
}

/** Transport/permission feedback remains independent of the conversation layout. */
export function MessageFeedback(props: WorldMessagePanelProps) {
  const { t } = useTranslation(props.lng);
  const { state } = props;
  return (
    <>
      {(state.status === 'unavailable' || props.feedback) && (
        <div
          role="status"
          className="flex flex-wrap items-center gap-2 rounded-lg border border-border p-2 text-sm"
        >
          {t('world.messages.offline')}
          <Button size="sm" variant="outline" className="min-h-11" onClick={props.onRetry}>
            {t('common.retry')}
          </Button>
        </div>
      )}
      {state.sending === 'rejected' && (
        <p role="status" className="text-sm text-destructive">
          {t('world.messages.rejected')}
        </p>
      )}
      {state.sending === 'uncertain' && (
        <div role="status" className="rounded-lg border border-border p-2 text-sm">
          <p>{t('world.messages.unknown_send')}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" className="min-h-11" onClick={props.onCheck}>
              {t('world.messages.check')}
            </Button>
            <Button size="sm" variant="outline" className="min-h-11" onClick={props.onDiscard}>
              {t(
                'world.messages.' + (state.operation === 'send' ? 'discard' : 'discard_translation')
              )}
            </Button>
          </div>
        </div>
      )}
      {!props.canSend && <p className="text-xs text-foreground/80">{t('world.messages.home')}</p>}
    </>
  );
}

'use client';

import { PUBLIC_THREAD } from './public-message-protocol';
import { ArrowLeft, MessageCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { MailboxClientState } from './mailbox-client';
import type { WorldParticipant } from './useWorldSession';
import { WorldMessageList } from './WorldMessageList';
import { WorldMessageForm } from './WorldMessageForm';
import type { MessageScrollStore } from './message-scroll-store';
import type { WorldConversation } from './conversation-directory';
import { WorldConversationDirectory } from './WorldConversationDirectory';

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
export function WorldMessagePanel(props: WorldMessagePanelProps) {
  const { t } = useTranslation(props.lng);
  const { state } = props;
  const publicMode = props.recipient === PUBLIC_THREAD;
  const publicAvailable = state.mailbox?.public_available;
  const busy = state.sending === 'sending' || state.sending === 'uncertain';
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <MessageFeedback {...props} />
      <div className="world-thread-layout" data-has-thread={Boolean(props.recipient)}>
        <WorldConversationDirectory
          lng={props.lng}
          conversations={props.conversations}
          recipient={props.recipient}
          publicState={publicDirectoryState(state, props.publicHasDraft)}
          busy={busy}
          onSelect={props.onRecipient}
        />
        {props.recipient ? (
          <div className="world-thread-detail">
            <Button
              variant="ghost"
              size="sm"
              className="world-thread-back min-h-11 w-fit shrink-0"
              disabled={busy}
              onClick={() => props.onRecipient('')}
            >
              <ArrowLeft className="size-4" aria-hidden="true" />
              {t('world.messages.conversations')}
            </Button>
            <div className="world-conversation-body grid min-h-0 flex-1 grid-rows-[minmax(64px,1fr)_minmax(0,auto)] gap-3">
              <WorldMessageList
                key={props.recipient}
                lng={props.lng}
                messages={threadMessages(state.mailbox, props.recipient)}
                publicMode={publicMode}
                tokensVisible={props.tokensVisible}
                canTranslate={props.consent && !busy && state.status === 'online'}
                onTranslate={props.onTranslate}
                scrollStore={props.scrollStore}
              />
              <WorldMessageForm
                lng={props.lng}
                publicMode={publicMode}
                participants={props.participants}
                draft={props.draft}
                recipient={props.recipient}
                recipientAlias={props.recipientAlias}
                consent={props.consent}
                enabled={composerEnabled(props)}
                busy={busy}
                onDraft={props.onDraft}
                onConsent={props.onConsent}
                onSubmit={props.onSubmit}
              />
            </div>
          </div>
        ) : (
          <div className="world-thread-welcome">
            <MessageCircle className="size-10 text-primary" aria-hidden="true" />
            <p>{t('world.messages.choose_conversation')}</p>
          </div>
        )}
      </div>
      {publicMode && publicAvailable === false && (
        <p role="status" className="text-xs text-muted-foreground">
          {t('world.public.unavailable')}
        </p>
      )}
      {(publicMode ? state.mailbox?.public_truncated : state.mailbox?.truncated) && (
        <p className="text-xs text-foreground/80">{t('world.messages.truncated')}</p>
      )}
    </div>
  );
}

function publicDirectoryState(state: MailboxClientState, hasDraft = false) {
  const available = state.mailbox?.public_available;
  if (available === undefined) return undefined;
  return { available, unread: state.unreadByRecipient[PUBLIC_THREAD] ?? 0, hasDraft };
}
function threadMessages(mailbox: MailboxClientState['mailbox'], recipient: string) {
  if (recipient === PUBLIC_THREAD) return mailbox?.public_messages ?? [];
  return (mailbox?.messages ?? []).filter(
    message => (message.outgoing ? message.recipient_id : message.sender_id) === recipient
  );
}
function composerEnabled(props: WorldMessagePanelProps): boolean {
  if (!props.canSend || props.state.status !== 'online') return false;
  return props.recipient !== PUBLIC_THREAD || props.state.mailbox?.public_available === true;
}

/** Transport/permission feedback remains independent of the conversation layout. */
function MessageFeedback(props: WorldMessagePanelProps) {
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

'use client';

import { PUBLIC_THREAD } from './public-message-protocol';
import { ArrowLeft, MessageCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { MailboxClientState } from './mailbox-client';
import { WorldMessageList } from './WorldMessageList';
import { WorldMessageForm } from './WorldMessageForm';
import { WorldConversationDirectory } from './WorldConversationDirectory';
import {
  MessageFeedback,
  composerEnabled,
  threadMessages,
  type WorldMessagePanelProps,
} from './WorldMessageFeedback';

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

'use client';

import {
  useCallback,
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
  type Ref,
} from 'react';
import dynamic from 'next/dynamic';
import { MessageCircle, ShieldCheck, ChevronDown, Megaphone } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAuth } from '@/hooks/useAuth';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { MailboxScope, MessageWrite } from './message-protocol';
import { messageText } from './message-protocol';
import type { WorldParticipant } from './useWorldSession';
import { useWorldMessages } from './useWorldMessages';
import { useWorldAccountIdentity, WorldPrivateActivity } from './WorldAccountGuard';
import { useWorldConversationDock, returnWorldFocus } from './useWorldConversationDock';
import { MessageScrollStore } from './message-scroll-store';
import type { MailboxClientState } from './mailbox-client';
import { PUBLIC_THREAD } from './public-message-protocol';
import { conversationDirectory } from './conversation-directory';

const MessagePanel = dynamic(
  () => import('./WorldMessagePanel').then(module => module.WorldMessagePanel),
  { ssr: false, loading: () => <Skeleton className="min-h-40 w-full flex-1" /> }
);
export interface WorldConversationHandle {
  canOpen(recipient: string): boolean;
  openFor(recipient: string): boolean;
}
interface Props {
  conversationRef?: Ref<WorldConversationHandle>;
  lng: Language;
  ownerId: string;
  enabled: boolean;
  canOpen: boolean;
  canSend: boolean;
  participants: WorldParticipant[];
  getScope(): MailboxScope | null;
  onOpen(value: boolean): void;
  onMailbox?(value: import('./message-protocol').WorldMailbox): void;
}
export function WorldMessageControls(props: Props) {
  return <OwnedMessageControls key={props.ownerId} {...props} />;
}
function OwnedMessageControls(props: Props) {
  const { user } = useAuth();
  const { verified } = useWorldAccountIdentity();
  const authorized = props.enabled && user?.id === props.ownerId && user.is_active;
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [recipient, setRecipient] = useState('');
  const [aliases, setAliases] = useState<Record<string, string>>({});
  const publicMode = recipient === PUBLIC_THREAD;
  const [consent, setConsent] = useThreadConsent(publicMode);
  const [feedback, setFeedback] = useState(false);
  const opener = useRef<HTMLElement | null>(null);
  const [scrollStores, setScrollStores] = useState<Record<string, MessageScrollStore>>(() => ({
    '': new MessageScrollStore(),
  }));
  const draft = drafts[recipient] ?? '';
  const scrollStore = scrollStores[recipient];
  const setDraft = (value: string) => setDrafts(current => ({ ...current, [recipient]: value }));
  const accepted = useCallback((intent: Readonly<MessageWrite>) => {
    const thread = 'recipient' in intent ? intent.recipient : PUBLIC_THREAD;
    setDrafts(current =>
      messageText(current[thread] ?? '') === intent.text ? { ...current, [thread]: '' } : current
    );
  }, []);
  const mailbox = useWorldMessages(props.ownerId, authorized, props.getScope, accepted);
  const { state, setReading } = mailbox;
  const { onMailbox } = props;
  useEffect(() => {
    if (state.mailbox) onMailbox?.(state.mailbox);
  }, [state.mailbox, onMailbox]);
  const { onOpen } = props;
  const available = authorized && props.canOpen;
  const shown = open && available;
  const dock = useWorldConversationDock(shown, 680, 640);
  const conversations = conversationDirectory(
    props.participants,
    state.mailbox?.messages ?? [],
    state.unreadByRecipient,
    drafts,
    aliases
  );
  const { t } = useTranslation(props.lng);
  const recipientAlias = selectedConversationAlias(
    conversations,
    aliases,
    recipient,
    t('world.public.title')
  );
  useEffect(() => {
    onOpen(shown);
    return () => onOpen(false);
  }, [shown, onOpen]);
  useEffect(() => {
    setReading(shown && verified && Boolean(recipient), recipient || null);
  }, [shown, verified, recipient, setReading]);
  function changeOpen(value: boolean) {
    setOpen(value);
    setFeedback(false);
  }
  const busy = state.sending === 'sending' || state.sending === 'uncertain';
  function selectRecipient(value: string): boolean {
    if (!available || !verified || busy) return false;
    if (
      value === PUBLIC_THREAD
        ? !state.mailbox?.public_available
        : value && !conversations.some(person => person.id === value)
    )
      return false;
    setScrollStores(current =>
      current[value] ? current : { ...current, [value]: new MessageScrollStore() }
    );
    const alias = conversations.find(person => person.id === value)?.alias;
    if (alias) setAliases(current => ({ ...current, [value]: alias }));
    setRecipient(value);
    setFeedback(false);
    return true;
  }
  useImperativeHandle(props.conversationRef, () => ({
    canOpen(value) {
      return Boolean(
        value &&
          available &&
          verified &&
          !busy &&
          props.participants.some(person => person.id === value)
      );
    },
    openFor(value) {
      if (!value || !selectRecipient(value)) return false;
      if (!shown && document.activeElement instanceof HTMLElement)
        opener.current = document.activeElement;
      changeOpen(true);
      return true;
    },
  }));
  async function send() {
    const outcome = publicMode
      ? await mailbox.sendPublic(draft, consent)
      : await mailbox.send(recipient, draft, consent);
    setFeedback(outcome === 'unavailable');
  }
  async function translate(id: string) {
    const outcome = await mailbox.translate(id, consent);
    setFeedback(outcome === 'unavailable');
  }
  return (
    <>
      <ConversationLauncher
        lng={props.lng}
        unread={state.unread}
        disabled={!available || !verified}
        onOpen={element => {
          opener.current = element;
          changeOpen(true);
        }}
      />
      <WorldPrivateActivity>
        <Dialog open={shown} onOpenChange={changeOpen} modal={false}>
          <DialogContent
            ref={dock}
            data-world-messages
            className="world-conversation flex flex-col overflow-hidden p-3 sm:p-4"
            onInteractOutside={event => event.preventDefault()}
            onCloseAutoFocus={event => {
              returnWorldFocus(event, opener.current);
            }}
          >
            <ConversationHeading
              lng={props.lng}
              alias={recipientAlias}
              mailbox={state.mailbox}
              publicMode={publicMode}
            />
            {shown && (
              <MessagePanel
                lng={props.lng}
                state={state}
                participants={props.participants}
                conversations={conversations}
                tokensVisible={user?.tokens_display_enabled ?? false}
                canSend={props.canSend}
                draft={draft}
                recipient={recipient}
                recipientAlias={recipientAlias}
                publicHasDraft={Boolean(drafts[PUBLIC_THREAD])}
                consent={consent}
                feedback={feedback}
                scrollStore={scrollStore}
                onDraft={setDraft}
                onRecipient={selectRecipient}
                onConsent={setConsent}
                onSubmit={() => {
                  void send();
                }}
                onTranslate={id => {
                  void translate(id);
                }}
                onCheck={() => {
                  void mailbox.check();
                }}
                onDiscard={() => {
                  if (state.operation === 'send') setDraft('');
                  mailbox.discard();
                }}
                onRetry={() => {
                  setFeedback(false);
                  mailbox.retry();
                }}
              />
            )}
          </DialogContent>
        </Dialog>
      </WorldPrivateActivity>
    </>
  );
}

function useThreadConsent(publicMode: boolean) {
  const privateConsent = useState(false),
    publicConsent = useState(false);
  return publicMode ? publicConsent : privateConsent;
}

function selectedConversationAlias(
  conversations: ReturnType<typeof conversationDirectory>,
  aliases: Readonly<Record<string, string>>,
  recipient: string,
  publicTitle: string
): string {
  if (recipient === PUBLIC_THREAD) return publicTitle;
  return conversations.find(person => person.id === recipient)?.alias ?? aliases[recipient] ?? '';
}

function ConversationLauncher({
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

function ConversationHeading({
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

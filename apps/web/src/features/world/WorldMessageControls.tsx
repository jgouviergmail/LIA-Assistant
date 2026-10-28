'use client';

import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react';
import dynamic from 'next/dynamic';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent } from '@/components/ui/dialog';
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
import { ConversationLauncher, ConversationHeading } from './WorldConversationChrome';
import { PUBLIC_THREAD } from './public-message-protocol';
import { conversationDirectory } from './conversation-directory';
import { WorldCompactConversation } from './WorldCompactConversation';
import { useCompactRecipient, AUTOMATIC_RECIPIENT } from './useCompactRecipient';
import { useCompactConversationDock } from './useCompactConversationDock';

const MessagePanel = dynamic(
  () => import('./WorldMessagePanel').then(module => module.WorldMessagePanel),
  { ssr: false, loading: () => <Skeleton className="min-h-40 w-full flex-1" /> }
);
export interface WorldConversationHandle {
  canOpen(recipient: string): boolean;
  openFor(recipient: string): boolean;
}
interface Props {
  compactHost?: HTMLElement | null;
  compactEnabled?: boolean;
  compactOnDemand?: boolean;
  onCompactOpen?(): void;
  nearbyParticipants?: readonly WorldParticipant[];
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
  const [open, setOpen] = useState(false);
  const [compactOpen, setCompactOpen] = useState(false);
  const { authorized, available, shown, compactShown } = messageVisibility(
    props,
    user,
    verified,
    open,
    compactOpen
  );
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [recipient, setRecipient] = useState('');
  const [aliases, setAliases] = useState<Record<string, string>>({});
  const publicMode = recipient === PUBLIC_THREAD;
  const privateConsent = useState(false),
    publicConsent = useState(false);
  const [consent, setConsent] = publicMode ? publicConsent : privateConsent;
  const [compactReading, setCompactReading] = useState(true);
  const [compactFocus, setCompactFocus] = useState(0);
  const compactFocused = useRef(0);
  const [feedback, setFeedback] = useState(false);
  const opener = useRef<HTMLElement | null>(null);
  const sendRecipient = useRef<string | null>(null);
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
  const busy = state.sending === 'sending' || state.sending === 'uncertain';
  const compact = useCompactRecipient(props.nearbyParticipants?.[0], drafts, busy);
  const [compactConsent, setCompactConsent] =
    compact.person.id === PUBLIC_THREAD ? publicConsent : privateConsent;
  const { onMailbox } = props;
  useEffect(() => {
    if (state.mailbox) onMailbox?.(state.mailbox);
  }, [state.mailbox, onMailbox]);
  const { onOpen } = props;
  useCompactConversationDock(props.compactHost ?? null, compactShown);
  const { compactHost } = props;
  useEffect(() => {
    // The launcher that opens the bar hands it the keyboard, once per press: the bar
    // sits before the session strip, where Tab from the launcher would never reach it.
    if (compactFocus <= compactFocused.current) return;
    compactFocused.current = compactFocus;
    if (compactShown)
      compactHost
        ?.querySelector<HTMLTextAreaElement>('textarea[name="world-message"]')
        ?.focus({ preventScroll: true });
  }, [compactFocus, compactShown, compactHost]);
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
    const reading =
      shown && verified ? recipient : compactShown && compactReading ? compact.person.id : '';
    setReading(Boolean(reading), reading || null);
  }, [shown, verified, recipient, setReading, compactShown, compactReading, compact.person.id]);
  function changeOpen(value: boolean) {
    setOpen(value);
    setFeedback(false);
  }
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
    if (value && props.compactHost) compact.select({ id: value, alias: alias ?? '' });
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
  async function sendTo(thread: string, text: string, permitted: boolean) {
    if (busy) return;
    sendRecipient.current = thread;
    const outcome =
      thread === PUBLIC_THREAD
        ? await mailbox.sendPublic(text, permitted)
        : await mailbox.send(thread, text, permitted);
    setFeedback(outcome === 'unavailable');
  }
  async function translate(id: string) {
    const outcome = await mailbox.translate(id, consent);
    setFeedback(outcome === 'unavailable');
  }
  function openCompactThread(element: HTMLElement) {
    compact.hold();
    compact.blur();
    setRecipient(compact.person.id);
    setScrollStores(current =>
      current[compact.person.id]
        ? current
        : { ...current, [compact.person.id]: new MessageScrollStore() }
    );
    if (compact.person.alias)
      setAliases(current => ({ ...current, [compact.person.id]: compact.person.alias }));
    opener.current = element;
    changeOpen(true);
  }
  function closeCompact() {
    setCompactOpen(false);
    compact.blur();
    props.compactHost?.parentElement
      ?.querySelector<HTMLButtonElement>('[data-world-conversations]')
      ?.focus({ preventScroll: true });
  }
  function discard() {
    const thread = sendRecipient.current ?? (shown ? recipient : compact.person.id);
    if (state.operation === 'send') setDrafts(current => ({ ...current, [thread]: '' }));
    mailbox.discard();
  }
  return (
    <>
      <WorldCompactConversation
        host={props.compactHost}
        shown={compactShown}
        dismissible={props.compactOnDemand}
        onClose={closeCompact}
        lng={props.lng}
        state={state}
        participants={props.participants}
        conversations={conversations}
        tokensVisible={false}
        canSend={props.canSend}
        draft={drafts[compact.person.id] ?? ''}
        recipient={compact.person.id}
        recipientAlias={compact.person.alias}
        selection={compact.value}
        consent={compactConsent}
        feedback={feedback}
        onReadingChange={setCompactReading}
        historyVisible={compactReading}
        onFocus={compact.focus}
        onBlur={compact.blur}
        onDraft={value => {
          compact.hold();
          setDrafts(current => ({ ...current, [compact.person.id]: value }));
          if (compact.person.alias)
            setAliases(current => ({
              ...current,
              [compact.person.id]: compact.person.alias,
            }));
        }}
        onRecipient={value => {
          if (busy) return;
          if (value === AUTOMATIC_RECIPIENT) compact.select(null);
          else if (value === PUBLIC_THREAD && state.mailbox?.public_available)
            compact.select({ id: value, alias: '' });
          else {
            const person = conversations.find(item => item.id === value);
            if (person) compact.select(person);
          }
          setFeedback(false);
        }}
        onConsent={setCompactConsent}
        onExpand={openCompactThread}
        onSubmit={() => {
          void sendTo(compact.person.id, drafts[compact.person.id] ?? '', compactConsent);
        }}
        onTranslate={id => {
          void mailbox.translate(id, compactConsent);
        }}
        onCheck={() => {
          void mailbox.check();
        }}
        onDiscard={discard}
        onRetry={() => {
          setFeedback(false);
          mailbox.retry();
        }}
      />
      <ConversationLauncher
        lng={props.lng}
        unread={state.unread}
        disabled={!available || !verified}
        onOpen={element => {
          if (props.compactOnDemand) {
            props.onCompactOpen?.();
            setCompactOpen(true);
            setCompactFocus(value => value + 1);
            compact.blur();
            changeOpen(false);
            return;
          }
          if (compactShown) {
            openCompactThread(element);
            return;
          }
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
              const target = opener.current?.isConnected
                ? opener.current
                : (props.compactHost?.querySelector<HTMLButtonElement>(
                    '[data-world-compact-expand]'
                  ) ?? null);
              returnWorldFocus(event, target);
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
                  void sendTo(recipient, draft, consent);
                }}
                onTranslate={id => {
                  void translate(id);
                }}
                onCheck={() => {
                  void mailbox.check();
                }}
                onDiscard={discard}
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

function messageVisibility(
  props: Props,
  user: ReturnType<typeof useAuth>['user'],
  verified: boolean,
  open: boolean,
  compactOpen: boolean
) {
  const authorized = props.enabled && user?.id === props.ownerId && user.is_active;
  const available = authorized && props.canOpen;
  const shown = open && available;
  const compactShown =
    !!props.compactHost &&
    props.compactEnabled !== false &&
    available &&
    verified &&
    props.canSend &&
    !shown &&
    (!props.compactOnDemand || compactOpen);
  return { authorized, available, shown, compactShown };
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

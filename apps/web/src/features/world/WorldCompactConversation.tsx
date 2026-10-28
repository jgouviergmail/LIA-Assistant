'use client';

import { useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { WorldPrivateActivity } from './WorldAccountGuard';
import { ChevronDown, ChevronUp, Languages, Maximize2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { useTranslation } from '@/i18n/client';
import { WorldMessageForm, WorldMessageConsent } from './WorldMessageForm';
import { WorldMessageList } from './WorldMessageList';
import {
  MessageFeedback,
  threadMessages,
  composerEnabled,
  type WorldMessagePanelProps,
} from './WorldMessageFeedback';
import { AUTOMATIC_RECIPIENT } from './useCompactRecipient';
import { PUBLIC_THREAD } from './public-message-protocol';
import { returnWorldFocus } from './useWorldConversationDock';
import './compact-chat.css';

interface Props extends WorldMessagePanelProps {
  dismissible?: boolean;
  onClose(): void;
  selection: string;
  onExpand(element: HTMLButtonElement): void;
  onFocus(): void;
  onBlur(): void;
  onReadingChange(value: boolean): void;
  historyVisible: boolean;
}

/** A second presentation of the existing mailbox, never a second connection. */
export function WorldCompactConversation({
  host,
  shown,
  ...props
}: Props & { host?: HTMLElement | null; shown: boolean }) {
  if (!host || !shown) return null;
  return createPortal(
    <WorldPrivateActivity>
      <OwnedCompactConversation {...props} />
    </WorldPrivateActivity>,
    host
  );
}

function OwnedCompactConversation(props: Props) {
  const { t } = useTranslation(props.lng);
  const collapsed = !props.historyVisible;
  const [permissionOpen, setPermissionOpen] = useState(false);
  const permissionOpener = useRef<HTMLElement | null>(null);
  const section = useRef<HTMLElement | null>(null);
  function openPermission(element?: HTMLElement) {
    permissionOpener.current =
      element ?? section.current?.querySelector('button[type="submit"]') ?? null;
    setPermissionOpen(true);
  }
  const publicMode = props.recipient === PUBLIC_THREAD;
  const busy = props.state.sending === 'sending' || props.state.sending === 'uncertain';
  const label = (id: string, alias: string) => {
    if (id === PUBLIC_THREAD) return `${t('world.compact.public')} · ${t('world.public.title')}`;
    const person = props.conversations.find(item => item.id === id);
    const name = person?.alias ?? alias;
    return `${t('world.compact.private')} · ${name}${person?.ambiguous ? ' #' + id.slice(-4) : ''}`;
  };
  const currentLabel = label(props.recipient, props.recipientAlias ?? '');
  return (
    <section
      ref={section}
      className="world-compact-chat"
      aria-label={t('world.compact.title')}
      data-collapsed={collapsed}
      onFocusCapture={props.onFocus}
      onBlurCapture={event => {
        if (!event.currentTarget.contains(event.relatedTarget)) props.onBlur();
      }}
    >
      <CompactHeading
        props={props}
        currentLabel={currentLabel}
        label={label}
        onPermission={openPermission}
      />
      {!collapsed && (
        <div className="world-compact-history">
          <WorldMessageList
            key={props.recipient}
            lng={props.lng}
            messages={threadMessages(props.state.mailbox, props.recipient)}
            publicMode={publicMode}
            tokensVisible={false}
            canTranslate={props.consent && !busy && props.state.status === 'online'}
            onTranslate={props.onTranslate}
            scrollStore={props.scrollStore}
          />
        </div>
      )}
      <div className="world-compact-feedback">
        <MessageFeedback {...props} />
        {publicMode && props.state.mailbox?.public_available === false && (
          <p role="status">{t('world.public.unavailable')}</p>
        )}
      </div>
      <WorldMessageForm
        lng={props.lng}
        compact
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
        onRequestConsent={() => openPermission()}
      />
      <Dialog open={permissionOpen} onOpenChange={setPermissionOpen}>
        <DialogContent
          onCloseAutoFocus={event => returnWorldFocus(event, permissionOpener.current)}
        >
          <DialogHeader>
            <DialogTitle>{t('world.messages.translation_details')}</DialogTitle>
            <DialogDescription>
              {t(publicMode ? 'world.public.translation_details' : 'world.messages.consent')}
            </DialogDescription>
          </DialogHeader>
          <WorldMessageConsent
            lng={props.lng}
            publicMode={publicMode}
            consent={props.consent}
            busy={busy}
            onConsent={props.onConsent}
            details={false}
          />
          <Button onClick={() => setPermissionOpen(false)}>{t('common.close')}</Button>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function CompactHeading({
  props,
  currentLabel,
  label,
  onPermission,
}: {
  props: Props;
  currentLabel: string;
  label(id: string, alias: string): string;
  onPermission(element?: HTMLElement): void;
}) {
  const { t } = useTranslation(props.lng);
  const collapsed = !props.historyVisible;
  const busy = props.state.sending === 'sending' || props.state.sending === 'uncertain';
  const people = props.conversations;
  const Collapse = collapsed ? ChevronUp : ChevronDown;
  return (
    <div className="world-compact-heading">
      <select
        className="world-compact-recipient"
        aria-label={t('world.compact.destination')}
        value={props.selection}
        aria-disabled={busy}
        onChange={event => {
          if (!busy) props.onRecipient(event.target.value);
        }}
      >
        <option value={AUTOMATIC_RECIPIENT}>
          {t('world.compact.auto')} · {currentLabel}
        </option>
        <option value={PUBLIC_THREAD} disabled={!props.state.mailbox?.public_available}>
          {label(PUBLIC_THREAD, '')}
        </option>
        {people.map(person => (
          <option key={person.id} value={person.id}>
            {label(person.id, person.alias)}
          </option>
        ))}
      </select>
      {!props.dismissible && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="world-compact-button"
          aria-label={t('world.messages.translation_details')}
          aria-haspopup="dialog"
          onClick={event => onPermission(event.currentTarget)}
        >
          <Languages
            className={props.consent ? 'size-4 text-primary' : 'size-4 text-muted-foreground'}
            aria-hidden="true"
          />
        </Button>
      )}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="world-compact-button"
        aria-label={t('world.compact.expand')}
        data-world-compact-expand
        onClick={event => props.onExpand(event.currentTarget)}
      >
        <Maximize2 className="size-4" aria-hidden="true" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="world-compact-button"
        aria-label={t(collapsed ? 'world.compact.show' : 'world.compact.hide')}
        aria-expanded={!collapsed}
        onClick={() => {
          props.onReadingChange(collapsed);
        }}
      >
        <Collapse className="size-4" aria-hidden="true" />
      </Button>
      {props.dismissible && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="world-compact-button"
          aria-label={t('world.compact.close')}
          onClick={props.onClose}
        >
          <X className="size-4" aria-hidden="true" />
        </Button>
      )}
    </div>
  );
}

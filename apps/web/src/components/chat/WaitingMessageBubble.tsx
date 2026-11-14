'use client';

/**
 * The person's words that wait for their turn, below the thread (ADR-384).
 *
 * The person's side of the chat, drawn as theirs but unsent: a dashed outline
 * instead of a filled bubble. One sentence says where it stands (announced
 * politely when it changes); the actions it offers come from
 * `waitingActions` — « Add to the answer in progress » first, while the answer
 * being written takes notes (ADR-385). A request on its way guards the buttons
 * without removing them, so the focus stays where the person left it.
 */

import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Clock, MessageSquarePlus, Pencil, Send, Trash2 } from '@/lib/icons';
import { CHAT_INPUT_MAX_LENGTH } from '@/lib/constants';
import { MonochromeIcons } from '@/lib/icon-style-context';
import {
  waitingActions,
  waitingLineKey,
  type WaitingMessage,
} from '@/lib/waiting-message';

export interface WaitingMessageBubbleProps {
  message: WaitingMessage;
  /** A question waits for the person's answer in this discussion. */
  questionPending: boolean;
  /** A request about this message is on its way. */
  pending: boolean;
  /** Replace the words; resolves false when the server refused them. */
  onEdit: (text: string) => Promise<boolean>;
  onWithdraw: () => void;
  onSendNow: () => void;
  /** Add it to the answer being written, as a note (ADR-385). */
  onJoin: () => void;
}

/** An edit belongs to the message as it was when the edit began. */
function stampOf(message: WaitingMessage): string {
  return `${message.version}:${message.status}`;
}

export function WaitingMessageBubble({
  message,
  questionPending,
  pending,
  onEdit,
  onWithdraw,
  onSendNow,
  onJoin,
}: WaitingMessageBubbleProps) {
  const { t } = useTranslation();
  // The draft carries the stamp it was opened under: once the message has
  // changed (left, came back held, was edited elsewhere) it is never shown again.
  const [draft, setDraft] = useState<{ text: string; stamp: string } | null>(null);
  const editButton = useRef<HTMLButtonElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const restoreFocus = useRef(false);
  const actions = waitingActions(message, questionPending);
  const editing = draft !== null && draft.stamp === stampOf(message) && actions.edit;

  useEffect(() => {
    if (editing) field.current?.focus();
    else if (restoreFocus.current) {
      restoreFocus.current = false;
      editButton.current?.focus();
    }
  }, [editing]);

  const closeEdit = () => {
    restoreFocus.current = true;
    setDraft(null);
  };

  const save = async () => {
    if (draft === null || pending) return;
    const text = draft.text.trim();
    if (text === '' || (await onEdit(text))) closeEdit();
  };

  const onFieldKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeEdit();
    }
  };

  return (
    <div
      role="group"
      aria-label={t('chat.waiting.label')}
      data-testid="waiting-message"
      className="flex gap-3 mb-4 flex-row"
    >
      <div className="flex-shrink-0">
        <div className="w-9 h-9 rounded-full flex items-center justify-center border border-dashed border-primary/60 text-primary">
          <MonochromeIcons>
            <Clock className="h-4 w-4" aria-hidden="true" />
          </MonochromeIcons>
        </div>
      </div>
      <div className="flex flex-col flex-1 items-start gap-1.5 min-w-0">
        {editing ? (
          <div className="w-full max-w-full space-y-2">
            <textarea
              ref={field}
              value={draft.text}
              maxLength={CHAT_INPUT_MAX_LENGTH}
              onChange={event => setDraft({ text: event.target.value, stamp: draft.stamp })}
              onKeyDown={onFieldKey}
              aria-label={t('chat.waiting.edit_label')}
              rows={3}
              className="block w-full resize-y rounded-lg border bg-background px-3 py-2 text-base mobile:text-sm"
            />
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" isLoading={pending} onClick={() => void save()}>
                {t('chat.waiting.save')}
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={closeEdit}>
                {t('chat.waiting.cancel')}
              </Button>
            </div>
          </div>
        ) : (
          <div className="message-bubble px-4 py-3 rounded-xl rounded-tl-none border border-dashed border-primary/60 bg-primary/5 text-foreground whitespace-pre-wrap break-words max-w-full">
            {message.content}
          </div>
        )}
        <p aria-live="polite" className="text-xs text-muted-foreground px-1">
          {t(waitingLineKey(message, questionPending))}
        </p>
        {!editing && (actions.edit || actions.withdraw || actions.sendNow || actions.join) && (
          <div className="flex flex-wrap gap-1.5">
            {actions.join && (
              <Button type="button" size="sm" isLoading={pending} onClick={onJoin}>
                <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden="true" />
                {t('chat.waiting.join')}
              </Button>
            )}
            {actions.sendNow && (
              <Button type="button" size="sm" isLoading={pending} onClick={onSendNow}>
                <Send className="h-3.5 w-3.5" aria-hidden="true" />
                {t('chat.waiting.send_now')}
              </Button>
            )}
            {actions.edit && (
              <Button
                ref={editButton}
                type="button"
                size="sm"
                variant="ghost"
                isLoading={pending}
                onClick={() => setDraft({ text: message.content, stamp: stampOf(message) })}
              >
                <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                {t('chat.waiting.edit')}
              </Button>
            )}
            {actions.withdraw && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="text-destructive"
                isLoading={pending}
                onClick={onWithdraw}
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                {t('chat.waiting.withdraw')}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * The bubble when something waits, nothing otherwise — so the chat page renders
 * it without a branch of its own (its render function is a frozen hotspot).
 */
export function WaitingMessageSlot({ bubble }: { bubble: WaitingMessageBubbleProps | null }) {
  return bubble === null ? null : <WaitingMessageBubble {...bubble} />;
}

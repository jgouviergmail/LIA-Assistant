'use client';

import {
  createContext,
  useContext,
  useMemo,
  type ReactNode,
  type ComponentPropsWithoutRef,
} from 'react';
import type { ExtraProps } from 'react-markdown';
import { useTranslation } from 'react-i18next';
import { cardActionsFromMetadata, cardCompositionWire } from '@/lib/card-actions';
import type {
  CardActionItem,
  CardActionsProjection,
  CardComposeAction,
  CardCompositionDraft,
} from '@/types/card-actions';

interface MessageActionContext {
  projection: CardActionsProjection | null;
  messageId?: string;
  onCompose?: (draft: CardCompositionDraft) => void;
}
const MessageActions = createContext<MessageActionContext>({ projection: null });
const ItemActions = createContext<CardActionItem | null>(null);

export function MessageCardActionsProvider({
  metadata,
  messageId,
  onCompose,
  children,
}: {
  metadata: unknown;
  messageId?: string;
  onCompose?: (draft: CardCompositionDraft) => void;
  children: ReactNode;
}) {
  const projection = useMemo(() => cardActionsFromMetadata(metadata), [metadata]);
  const value = useMemo(
    () => ({ projection, messageId, onCompose }),
    [projection, messageId, onCompose]
  );
  return <MessageActions.Provider value={value}>{children}</MessageActions.Provider>;
}

export function MarkdownCardBinding({
  node,
  children,
  ...props
}: ComponentPropsWithoutRef<'div'> & ExtraProps) {
  const { projection } = useContext(MessageActions);
  const reference = node?.properties.dataCardRef;
  const item =
    typeof reference === 'string'
      ? (projection?.items.find(target => target.registry_id === reference) ?? null)
      : null;
  return (
    <ItemActions.Provider value={item}>
      <div {...props}>{children}</div>
    </ItemActions.Provider>
  );
}

function supportedAction(value: unknown): CardComposeAction | null {
  if (typeof value !== 'string') return null;
  const key = value.split(':', 1)[0];
  return key === 'reply' || key === 'forward' || key === 'delete_email' || key === 'cancel_reminder'
    ? key
    : null;
}

export function MarkdownCardButton({
  node,
  children,
  ...props
}: ComponentPropsWithoutRef<'button'> & ExtraProps) {
  const { t } = useTranslation();
  const { projection, messageId, onCompose } = useContext(MessageActions);
  const item = useContext(ItemActions);
  const action = supportedAction(node?.properties.dataAction);
  const selection = cardCompositionWire({
    version: 1,
    message_id: messageId,
    run_id: projection?.run_id,
    registry_id: item?.registry_id,
    action,
  });
  const enabled = Boolean(
    item && action && item.actions.includes(action) && selection && onCompose && !props.disabled
  );
  return (
    <button
      {...props}
      type="button"
      disabled={!enabled}
      title={!enabled ? t('chat.card_actions.unavailable') : t('chat.card_actions.editable')}
      onClick={() => {
        if (enabled && item && action && selection)
          onCompose?.({
            text: t(`chat.card_actions.compose_${action}`),
            label: item.label,
            selection,
          });
      }}
    >
      {enabled && action ? (
        <>
          <span className="material-symbols-outlined" aria-hidden="true">
            {action === 'reply' ? 'reply' : action === 'forward' ? 'forward' : 'delete'}
          </span>
          {t(`chat.card_actions.${action}`)}
        </>
      ) : (
        children
      )}
    </button>
  );
}

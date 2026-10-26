'use client';

import { MessageCircle, PencilLine, UsersRound, Megaphone } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { PUBLIC_THREAD } from './public-message-protocol';
import type { WorldConversation } from './conversation-directory';

export function WorldConversationDirectory({
  lng,
  conversations,
  recipient,
  busy,
  publicState,
  onSelect,
}: {
  lng: Language;
  conversations: readonly WorldConversation[];
  recipient: string;
  busy: boolean;
  publicState?: { available: boolean; unread: number; hasDraft: boolean };
  onSelect(id: string): void;
}) {
  const { t } = useTranslation(lng);
  return (
    <nav className="world-conversation-directory" aria-label={t('world.messages.conversations')}>
      <p className="flex items-center gap-2 px-2 pb-3 text-xs font-semibold">
        <UsersRound className="size-4 text-primary" aria-hidden="true" />
        {t('world.messages.conversations')}
      </p>
      {publicState && (
        <Button
          variant="ghost"
          disabled={busy || !publicState.available}
          aria-current={recipient === PUBLIC_THREAD ? 'page' : undefined}
          className="world-conversation-person mb-3 border border-primary/20 bg-primary/5"
          onClick={() => onSelect(PUBLIC_THREAD)}
        >
          <span className="world-person-avatar text-primary" aria-hidden="true">
            <Megaphone className="size-5" />
          </span>
          <span className="min-w-0 flex-1 text-left">
            <span className="flex items-center gap-1 font-semibold">
              {t('world.public.title')}
              {publicState.hasDraft && (
                <PencilLine className="size-3" aria-label={t('world.messages.draft')} />
              )}
            </span>
            <span className="block text-xs font-normal text-muted-foreground">
              {t('world.public.caption')}
            </span>
          </span>
          {publicState.unread > 0 && (
            <span className="world-thread-unread">
              <span aria-hidden="true">{publicState.unread}</span>
              <span className="sr-only">
                {t('world.messages.unread', { count: publicState.unread })}
              </span>
            </span>
          )}
        </Button>
      )}
      {conversations.length === 0 && (
        <p className="p-3 text-sm text-muted-foreground">{t('world.messages.no_peers')}</p>
      )}
      <ul className="space-y-1">
        {conversations.map(person => (
          <li key={person.id}>
            <Button
              variant="ghost"
              disabled={busy}
              aria-current={recipient === person.id ? 'page' : undefined}
              className="world-conversation-person"
              onClick={() => onSelect(person.id)}
            >
              <span className="world-person-avatar" aria-hidden="true">
                {Array.from(person.alias.trim()).slice(0, 2).join('').toLocaleUpperCase(lng)}
                <span className={person.online ? 'world-person-online' : 'world-person-offline'} />
              </span>
              <span className="min-w-0 flex-1 text-left">
                <span className="flex items-center gap-1">
                  <span className="truncate font-semibold" dir="auto">
                    {person.alias}
                  </span>
                  {person.ambiguous && (
                    <span className="text-[10px] text-muted-foreground">
                      #{person.id.slice(-4)}
                    </span>
                  )}
                  {person.hasDraft && (
                    <PencilLine
                      className="size-3 shrink-0 text-primary"
                      aria-label={t('world.messages.draft')}
                    />
                  )}
                </span>
                <span
                  className="block truncate text-xs font-normal text-muted-foreground"
                  dir="auto"
                >
                  {person.preview !== null
                    ? (person.latest?.outgoing ? t('world.messages.you') + ': ' : '') +
                      person.preview
                    : person.latest
                      ? t('world.messages.' + person.latest.status)
                      : t(
                          person.online
                            ? 'world.messages.start_conversation'
                            : 'world.messages.left'
                        )}
                </span>
                <span className="sr-only">
                  {t(person.online ? 'world.messages.present' : 'world.messages.left')}
                </span>
              </span>
              {person.unread > 0 && (
                <span className="world-thread-unread">
                  <span aria-hidden="true">{person.unread}</span>
                  <span className="sr-only">
                    {t('world.messages.unread', { count: person.unread })}
                  </span>
                </span>
              )}
              {!person.latest && (
                <MessageCircle className="size-4 shrink-0 text-primary" aria-hidden="true" />
              )}
            </Button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

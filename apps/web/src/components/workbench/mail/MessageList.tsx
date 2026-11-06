'use client';

/**
 * MessageList — one folder's messages (ADR-369, Task 4.7).
 *
 * A skeleton on the first read only (a refresh keeps the rows on screen), the
 * way out when the folder is empty or the search found nothing, the reason
 * when the read failed. « Older messages » exactly when the provider has more,
 * and a line saying how many messages the provider listed but could not read
 * (ADR-185: a cut is stated). The arrows move between messages, Home and End
 * to the first and the last; Enter opens the one in focus (it is a link). A line
 * is a message, or a conversation under its newest one (`mailLines`): it is the
 * open line whichever of its messages is open, and its link gets the focus back.
 */
import { Inbox, SearchX } from 'lucide-react';
import type { KeyboardEvent } from 'react';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import type { MailDensity, MailLine } from '@/lib/workbench/mail';
import type { MailSummary } from '@/lib/workbench/types';

import { MessageRow, type MessageRowProps } from './MessageRow';

const ROW_LINK = 'a[data-mail-row]';

export interface MessageListProps {
  lng: Language;
  messages: WorkbenchPageState<MailSummary>;
  /** What is loaded, as lines. */
  lines: readonly MailLine[];
  openId: string | null;
  selected: ReadonlySet<string>;
  selectable: boolean;
  density: MailDensity;
  /** Something narrows the listing (words or chips): an empty answer is « no match ». */
  searching: boolean;
  whenOf: (message: MailSummary) => string | null;
  labelName: MessageRowProps['labelName'];
  hrefOf: (message: MailSummary) => string;
  onOpen: (message: MailSummary) => void;
  onToggle: MessageRowProps['onToggle'];
  onRead: MessageRowProps['onRead'];
  moves: MessageRowProps['moves'];
  onStar: MessageRowProps['onStar'];
  onSend: MessageRowProps['onSend'];
  onMove: MessageRowProps['onMove'];
  onForever: MessageRowProps['onForever'];
  /** From `lg`, with a mouse, a row can be dragged to a folder. */
  draggable: boolean;
  onClearSearch: () => void;
  linkRef: MessageRowProps['linkRef'];
}

/** The arrows, Home and End move the focus between the rows' links. */
function moveFocus(event: KeyboardEvent<HTMLUListElement>): void {
  const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End'];
  if (!keys.includes(event.key)) return;
  const links = Array.from(event.currentTarget.querySelectorAll<HTMLAnchorElement>(ROW_LINK));
  const at = links.findIndex(link => link === document.activeElement);
  if (at < 0 || links.length === 0) return;
  event.preventDefault();
  const next = {
    ArrowDown: Math.min(at + 1, links.length - 1),
    ArrowUp: Math.max(at - 1, 0),
    Home: 0,
    End: links.length - 1,
  }[event.key];
  links[next ?? at]?.focus();
}

export function MessageList({
  lng,
  messages,
  lines,
  openId,
  selected,
  selectable,
  density,
  searching,
  whenOf,
  labelName,
  hrefOf,
  onOpen,
  onToggle,
  onRead,
  moves,
  onStar,
  onSend,
  onMove,
  onForever,
  draggable,
  onClearSearch,
  linkRef,
}: MessageListProps) {
  const { t } = useTranslation(lng);
  if (messages.loading) {
    return (
      <div className="space-y-2 p-4" aria-busy="true">
        {[1, 2, 3, 4, 5].map(index => (
          <Skeleton key={index} className="h-14 w-full" />
        ))}
      </div>
    );
  }
  if (messages.items.length === 0) {
    if (messages.error) {
      return (
        <EmptyState
          description={t('workbench.mail.failed')}
          action={{ label: t('workbench.states.retry'), onClick: () => void messages.refresh() }}
        />
      );
    }
    return searching ? (
      <EmptyState
        icon={SearchX}
        title={t('workbench.mail.no_match_title')}
        action={{ label: t('workbench.mail.search_clear'), onClick: onClearSearch }}
      />
    ) : (
      <EmptyState icon={Inbox} title={t('workbench.mail.empty_title')} />
    );
  }
  return (
    <div aria-busy={messages.loadingMore || undefined} className="min-h-0 flex-1 overflow-y-auto">
      <ul aria-label={t('workbench.mail.messages_title')} onKeyDown={moveFocus}>
        {lines.map(({ message, members }) => (
          <MessageRow
            key={message.id}
            lng={lng}
            message={message}
            when={whenOf(message)}
            open={members.some(member => member.id === openId)}
            selected={selected.has(message.id)}
            selectable={selectable}
            density={density}
            narrow={openId !== null}
            labelName={labelName}
            href={hrefOf(message)}
            onOpen={onOpen}
            onToggle={onToggle}
            onRead={onRead}
            moves={moves}
            onStar={onStar}
            onSend={onSend}
            onMove={onMove}
            onForever={onForever}
            draggable={draggable}
            conversation={members.length > 1}
            linkRef={(_, link) => members.forEach(member => linkRef(member.id, link))}
          />
        ))}
      </ul>
      {messages.skipped > 0 && (
        <p role="status" className="px-4 pt-3 text-sm text-muted-foreground">
          {t('workbench.mail.skipped', { count: messages.skipped })}
        </p>
      )}
      {messages.error !== null && (
        <p role="status" className="px-4 pt-3 text-sm text-destructive">
          {t('workbench.mail.failed')}
        </p>
      )}
      {messages.nextToken && (
        <div className="p-3 text-center">
          <Button
            variant="outline"
            size="sm"
            isLoading={messages.loadingMore}
            onClick={() => void messages.loadMore()}
          >
            {t('workbench.mail.load_more')}
          </Button>
        </div>
      )}
    </div>
  );
}

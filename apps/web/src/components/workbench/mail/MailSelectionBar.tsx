'use client';

/**
 * MailSelectionBar — acts on the selected messages (ADR-369, mock-up « Main »).
 *
 * Mark read or unread, star, label (Gmail), and what `movesFrom` offers from this
 * folder: each on every selected message, each answered message by message: the
 * screen says what was done and what was not. A selection beyond the published
 * bulk bound is stated and refused before anything is sent (`limits.bulk_max_items`,
 * ADR-184). Sending to the trash needs no dialog: a trashed message can be restored;
 * deleting for good asks first.
 */
import {
  Archive,
  ArchiveRestore,
  FolderInput,
  Inbox,
  MailCheck,
  MailOpen,
  OctagonAlert,
  Star,
  Trash2,
  type LucideIcon,
} from '@/lib/icons';

import { Button } from '@/components/ui/button';
import { SelectionBar } from '@/components/ui/selection-bar';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PageSelectionState } from '@/lib/selection';
import type { MailMoves, MailSendAct } from '@/lib/workbench/mail';
import type { MailFolder, MailSummary } from '@/lib/workbench/types';

import { LabelMenu } from './LabelMenu';

/** Which act is on its way, if any. */
export type MailBulkAct = 'read' | 'unread' | 'star' | 'labels' | 'forever' | 'empty' | MailSendAct;

export interface MailSelectionBarProps {
  lng: Language;
  selected: readonly MailSummary[];
  pageState: PageSelectionState;
  bulkMax: number;
  /** The person's labels where the provider has labels; undefined elsewhere. */
  labels: readonly MailFolder[] | undefined;
  busy: MailBulkAct | null;
  /** What the folder offers. */
  moves: MailMoves;
  onSelectAll: () => void;
  onClear: () => void;
  onRead: (read: boolean) => void;
  onStar: (starred: boolean) => void;
  onLabels: (add: string[], remove: string[]) => void;
  onSend: (act: MailSendAct) => void;
  /** Opens the folder picker. */
  onMove: () => void;
  onForever: () => void;
}

export function MailSelectionBar({
  lng,
  selected,
  pageState,
  bulkMax,
  labels,
  busy,
  moves,
  onSelectAll,
  onClear,
  onRead,
  onStar,
  onLabels,
  onSend,
  onMove,
  onForever,
}: MailSelectionBarProps) {
  const { t } = useTranslation(lng);
  const over = selected.length > bulkMax;
  const held = over || busy !== null;
  // A guard, not the attribute: `aria-disabled` keeps the focus where it is.
  const guarded = (act: () => void) => () => {
    if (!held) act();
  };
  const allStarred = selected.length > 0 && selected.every(row => row.is_starred);
  const offered: {
    act: MailBulkAct;
    key: string;
    icon: LucideIcon;
    run: () => void;
    on: boolean;
  }[] = [
    {
      act: 'star',
      key: allStarred ? 'workbench.mail.bar_unstar' : 'workbench.mail.bar_star',
      icon: Star,
      run: () => onStar(!allStarred),
      on: true,
    },
    {
      act: 'archive',
      key: 'workbench.mail.archive',
      icon: Archive,
      run: () => onSend('archive'),
      on: moves.archive,
    },
    {
      act: 'restore',
      key: 'workbench.mail.restore',
      icon: ArchiveRestore,
      run: () => onSend('restore'),
      on: moves.restore,
    },
    {
      act: 'not_spam',
      key: 'workbench.mail.not_spam',
      icon: Inbox,
      run: () => onSend('not_spam'),
      on: moves.notSpam,
    },
    {
      act: 'move',
      key: 'workbench.mail.move_to',
      icon: FolderInput,
      run: onMove,
      on: moves.move,
    },
    {
      act: 'spam',
      key: 'workbench.mail.bar_spam',
      icon: OctagonAlert,
      run: () => onSend('spam'),
      on: moves.spam,
    },
  ];
  return (
    <div className="border-b px-4 py-2">
      <SelectionBar
        regionLabel={t('workbench.mail.selection_region')}
        countLabel={t('workbench.mail.selected', { count: selected.length })}
        selectAllLabel={t('workbench.mail.select_page')}
        clearLabel={t('workbench.mail.clear_selection')}
        pageState={pageState}
        onSelectAll={onSelectAll}
        onClear={onClear}
      >
        <Button
          size="sm"
          variant="outline"
          aria-disabled={held || undefined}
          isLoading={busy === 'read'}
          onClick={guarded(() => onRead(true))}
          className="gap-1.5"
        >
          <MailCheck className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.bar_read')}
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-disabled={held || undefined}
          isLoading={busy === 'unread'}
          onClick={guarded(() => onRead(false))}
          className="gap-1.5"
        >
          <MailOpen className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.bar_unread')}
        </Button>
        {offered
          .filter(item => item.on)
          .map(({ act, key, icon: Icon, run }) => (
            <Button
              key={act}
              size="sm"
              variant="outline"
              aria-disabled={held || undefined}
              isLoading={busy === act}
              onClick={guarded(run)}
              className="gap-1.5"
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {t(key)}
            </Button>
          ))}
        {labels && (
          <LabelMenu
            lng={lng}
            labels={labels}
            messages={selected}
            busy={held}
            onApply={(add, remove) => onLabels(add, remove)}
          />
        )}
        {moves.forever ? (
          <Button
            size="sm"
            variant="destructive"
            aria-disabled={held || undefined}
            isLoading={busy === 'forever'}
            onClick={guarded(onForever)}
            className="gap-1.5"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            {t('workbench.mail.delete_forever')}
          </Button>
        ) : (
          !moves.restore && (
            <Button
              size="sm"
              variant="destructive"
              aria-disabled={held || undefined}
              isLoading={busy === 'trash'}
              onClick={guarded(() => onSend('trash'))}
              className="gap-1.5"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              {t('workbench.mail.trash')}
            </Button>
          )
        )}
      </SelectionBar>
      {over && (
        <p role="status" className="px-1 pt-2 text-sm text-destructive">
          {t('workbench.mail.over_bulk', { count: bulkMax })}
        </p>
      )}
    </div>
  );
}

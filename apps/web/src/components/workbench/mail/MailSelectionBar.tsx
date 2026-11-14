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
 *
 * It only declares what it offers: `ToolSelectionBar` draws it on one line (amendment
 * 2026-11-11). Marking read and the folder's own way out are what a sorting uses most;
 * each act says itself in the words and under the icon of the reader and of the rows.
 */
import {
  Archive,
  ArchiveRestore,
  FolderInput,
  Inbox,
  Mail,
  MailOpen,
  OctagonAlert,
  Star,
  Tag,
  Trash2,
} from '@/lib/icons';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PageSelectionState } from '@/lib/selection';
import type { MailMoves, MailSendAct } from '@/lib/workbench/mail';
import type { MailFolder, MailSummary } from '@/lib/workbench/types';

import { ToolSelectionBar, type SelectionAct } from '../ToolSelectionBar';
import { LabelLines } from './LabelMenu';

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

/** One act the bar may offer: its word, and whether this folder and this mailbox have it. */
interface Offered extends Omit<SelectionAct, 'id' | 'label' | 'busy'> {
  id: MailBulkAct;
  key: string;
  on: boolean;
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
  const allStarred = selected.length > 0 && selected.every(row => row.is_starred);
  const send = (act: MailSendAct) => () => onSend(act);
  const offered: Offered[] = [
    {
      id: 'read',
      key: 'workbench.mail.mark_read',
      icon: MailOpen,
      onSelect: () => onRead(true),
      quick: true,
      on: true,
    },
    {
      id: 'unread',
      key: 'workbench.mail.mark_unread',
      icon: Mail,
      onSelect: () => onRead(false),
      on: true,
    },
    {
      id: 'star',
      key: allStarred ? 'workbench.mail.unstar' : 'workbench.mail.star',
      icon: Star,
      onSelect: () => onStar(!allStarred),
      on: true,
    },
    {
      id: 'archive',
      key: 'workbench.mail.archive',
      icon: Archive,
      onSelect: send('archive'),
      quick: true,
      on: moves.archive,
    },
    {
      id: 'restore',
      key: 'workbench.mail.restore',
      icon: ArchiveRestore,
      onSelect: send('restore'),
      quick: true,
      on: moves.restore,
    },
    {
      id: 'not_spam',
      key: 'workbench.mail.not_spam',
      icon: Inbox,
      onSelect: send('not_spam'),
      quick: true,
      on: moves.notSpam,
    },
    {
      id: 'move',
      key: 'workbench.mail.move_to',
      icon: FolderInput,
      onSelect: onMove,
      on: moves.move,
    },
    {
      id: 'spam',
      key: 'workbench.mail.report_spam',
      icon: OctagonAlert,
      onSelect: send('spam'),
      on: moves.spam,
    },
    {
      id: 'labels',
      key: 'workbench.mail.labels_title',
      icon: Tag,
      lines: labels && (
        <LabelLines lng={lng} labels={labels} messages={selected} busy={held} onApply={onLabels} />
      ),
      on: labels !== undefined,
    },
    {
      id: 'forever',
      key: 'workbench.mail.delete_forever',
      icon: Trash2,
      onSelect: onForever,
      danger: true,
      on: moves.forever,
    },
    {
      // What is in the trash already leaves it for good, or not from here.
      id: 'trash',
      key: 'workbench.mail.trash',
      icon: Trash2,
      onSelect: send('trash'),
      danger: true,
      on: !moves.forever && !moves.restore,
    },
  ];
  return (
    <ToolSelectionBar
      lng={lng}
      regionLabel={t('workbench.mail.selection_region')}
      countLabel={t('workbench.mail.selected', { count: selected.length })}
      selectAllLabel={t('workbench.mail.select_page')}
      clearLabel={t('workbench.mail.clear_selection')}
      pageState={pageState}
      onSelectAll={onSelectAll}
      onClear={onClear}
      acts={offered
        .filter(item => item.on)
        .map(({ key, on: _on, ...act }) => ({ ...act, label: t(key), busy: busy === act.id }))}
      held={held}
      note={over ? t('workbench.mail.over_bulk', { count: bulkMax }) : undefined}
    />
  );
}

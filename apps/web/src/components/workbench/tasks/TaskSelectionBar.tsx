'use client';

/**
 * What ticked tasks can become (ADR-369, lot 9): done, not done, deleted after a question, or
 * sent to another list. Each act answers task by task (`useTaskSelection` tells it): what was
 * done leaves the selection, what could not be stays ticked. While an act runs the others wait.
 *
 * It only declares what it offers: `ToolSelectionBar` draws it on one line (amendment
 * 2026-11-11). Another list is a place: the lists stand under their own line.
 */
import { Check, FolderInput, RotateCcw, Trash2 } from '@/lib/icons';

import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PageSelectionState } from '@/lib/selection';
import type { WorkbenchTaskList } from '@/lib/workbench/types';

import { ToolSelectionBar, type SelectionAct } from '../ToolSelectionBar';

export interface TaskSelectionBarProps {
  lng: Language;
  count: number;
  pageState: PageSelectionState;
  /** The lists a selection can go to. */
  others: readonly WorkbenchTaskList[];
  busy: boolean;
  onSelectAll: () => void;
  onClear: () => void;
  onCompleted: (completed: boolean) => void;
  onDelete: () => void;
  onMove: (destination: string) => void;
}

export function TaskSelectionBar({
  lng,
  count,
  pageState,
  others,
  busy,
  onSelectAll,
  onClear,
  onCompleted,
  onDelete,
  onMove,
}: TaskSelectionBarProps) {
  const { t } = useTranslation(lng);
  const move: SelectionAct = {
    id: 'move',
    label: t('workbench.tasks.move_to_list'),
    icon: FolderInput,
    lines: others.map(list => (
      <DropdownMenuItem key={list.id} disabled={busy} onSelect={() => onMove(list.id)}>
        {list.title || t('workbench.tasks.untitled')}
      </DropdownMenuItem>
    )),
  };
  const acts: SelectionAct[] = [
    {
      id: 'complete',
      label: t('workbench.tasks.complete_selection'),
      icon: Check,
      onSelect: () => onCompleted(true),
      quick: true,
    },
    {
      id: 'reopen',
      label: t('workbench.tasks.reopen_selection'),
      icon: RotateCcw,
      onSelect: () => onCompleted(false),
    },
    ...(others.length > 0 ? [move] : []),
    { id: 'delete', label: t('common.delete'), icon: Trash2, onSelect: onDelete, danger: true },
  ];
  return (
    <ToolSelectionBar
      lng={lng}
      regionLabel={t('workbench.tasks.selection_region')}
      countLabel={t('workbench.tasks.selected', { count })}
      selectAllLabel={t('workbench.tasks.select_page')}
      clearLabel={t('workbench.tasks.clear_selection')}
      pageState={pageState}
      onSelectAll={onSelectAll}
      onClear={onClear}
      acts={acts}
      held={busy}
    />
  );
}

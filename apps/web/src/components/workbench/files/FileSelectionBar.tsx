'use client';

/**
 * FileSelectionBar — acts on the items ticked (ADR-369, lot 2).
 *
 * The exact count, the page at once, the move and the trash; a rename for one item,
 * the only way to a folder's, and a copy for one file: Drive copies no folder. In the
 * trash, what comes back and what leaves for good, and nothing else. A selection past
 * the published bound is said and sends nothing (`limits.bulk_max_items`, ADR-184).
 *
 * It only declares what it offers: `ToolSelectionBar` draws it on one line (amendment
 * 2026-11-11).
 */
import { Copy, FolderInput, Pencil, RotateCcw, Trash2 } from '@/lib/icons';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { pageSelectionState } from '@/lib/selection';
import type { WorkbenchDriveItem } from '@/lib/workbench/types';

import { ToolSelectionBar, type SelectionAct } from '../ToolSelectionBar';

export interface FileSelectionBarProps {
  lng: Language;
  /** The ids of the page, in its order. */
  rows: readonly string[];
  selected: ReadonlySet<string>;
  bulkMax: number;
  /** The item ticked alone, if it is on the page. */
  only: WorkbenchDriveItem | null;
  /** The list is the drive's trash. */
  inTrash: boolean;
  onSelect: (ids: ReadonlySet<string>) => void;
  onTrash: () => void;
  onRestore: () => void;
  onDeleteForever: () => void;
  onMove: () => void;
  onRename: (item: WorkbenchDriveItem) => void;
  onCopy: (item: WorkbenchDriveItem) => void;
}

/** One act the bar may offer: its word, and whether this list and this selection have it. */
interface Offered extends Omit<SelectionAct, 'label'> {
  key: string;
  on: boolean;
}

export function FileSelectionBar({
  lng,
  rows,
  selected,
  bulkMax,
  only,
  inTrash,
  onSelect,
  onTrash,
  onRestore,
  onDeleteForever,
  onMove,
  onRename,
  onCopy,
}: FileSelectionBarProps) {
  const { t } = useTranslation(lng);
  const over = selected.size > bulkMax;
  const offered: Offered[] = [
    {
      id: 'restore',
      key: 'workbench.files.restore',
      icon: RotateCcw,
      onSelect: onRestore,
      quick: true,
      on: inTrash,
    },
    {
      id: 'move',
      key: 'workbench.files.move',
      icon: FolderInput,
      onSelect: onMove,
      quick: true,
      on: !inTrash,
    },
    {
      id: 'rename',
      key: 'workbench.files.rename',
      icon: Pencil,
      onSelect: () => only && onRename(only),
      on: !inTrash && only !== null,
    },
    {
      id: 'copy',
      key: 'workbench.files.copy',
      icon: Copy,
      onSelect: () => only && onCopy(only),
      on: !inTrash && only?.kind === 'file',
    },
    {
      id: 'forever',
      key: 'workbench.files.delete_forever',
      icon: Trash2,
      onSelect: onDeleteForever,
      danger: true,
      on: inTrash,
    },
    {
      id: 'trash',
      key: 'workbench.files.trash',
      icon: Trash2,
      onSelect: onTrash,
      danger: true,
      on: !inTrash,
    },
  ];
  return (
    <ToolSelectionBar
      lng={lng}
      regionLabel={t('workbench.files.selection_region')}
      countLabel={t('workbench.files.selected', { count: selected.size })}
      selectAllLabel={t('workbench.files.select_page')}
      clearLabel={t('workbench.files.clear_selection')}
      pageState={pageSelectionState(rows, selected)}
      onSelectAll={() => onSelect(new Set(rows))}
      onClear={() => onSelect(new Set())}
      acts={offered
        .filter(item => item.on)
        .map(({ key, on: _on, ...act }) => ({ ...act, label: t(key) }))}
      held={over}
      note={over ? t('workbench.files.over_bulk', { count: bulkMax }) : undefined}
    />
  );
}

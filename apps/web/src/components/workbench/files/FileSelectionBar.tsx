'use client';

/**
 * FileSelectionBar — acts on the items ticked (ADR-369, lot 2).
 *
 * The exact count, the page at once, the move and the trash; a rename for one item,
 * the only way to a folder's, and a copy for one file: Drive copies no folder. In the
 * trash, what comes back and what leaves for good, and nothing else. A selection past
 * the published bound is said and sends nothing (`limits.bulk_max_items`, ADR-184).
 */
import { Copy, FolderInput, Pencil, RotateCcw, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { SelectionBar } from '@/components/ui/selection-bar';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { pageSelectionState } from '@/lib/selection';
import type { WorkbenchDriveItem } from '@/lib/workbench/types';

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
  return (
    <div className="border-b px-3 py-2">
      <SelectionBar
        regionLabel={t('workbench.files.selection_region')}
        countLabel={t('workbench.files.selected', { count: selected.size })}
        selectAllLabel={t('workbench.files.select_page')}
        clearLabel={t('workbench.files.clear_selection')}
        pageState={pageSelectionState(rows, selected)}
        onSelectAll={() => onSelect(new Set(rows))}
        onClear={() => onSelect(new Set())}
      >
        {inTrash && (
          <Button
            size="sm"
            variant="outline"
            aria-disabled={over || undefined}
            onClick={() => {
              if (!over) onRestore();
            }}
            className="gap-1.5"
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            {t('workbench.files.restore')}
          </Button>
        )}
        {inTrash && (
          <Button
            size="sm"
            variant="destructive"
            aria-disabled={over || undefined}
            onClick={() => {
              if (!over) onDeleteForever();
            }}
            className="gap-1.5"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            {t('workbench.files.delete_forever')}
          </Button>
        )}
        {!inTrash && only && (
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => onRename(only)}>
            <Pencil className="h-4 w-4" aria-hidden="true" />
            {t('workbench.files.rename')}
          </Button>
        )}
        {!inTrash && only?.kind === 'file' && (
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => onCopy(only)}>
            <Copy className="h-4 w-4" aria-hidden="true" />
            {t('workbench.files.copy')}
          </Button>
        )}
        {!inTrash && (
          <Button
            size="sm"
            variant="outline"
            aria-disabled={over || undefined}
            onClick={() => {
              if (!over) onMove();
            }}
            className="gap-1.5"
          >
            <FolderInput className="h-4 w-4" aria-hidden="true" />
            {t('workbench.files.move')}
          </Button>
        )}
        {!inTrash && (
          <Button
            size="sm"
            variant="destructive"
            aria-disabled={over || undefined}
            onClick={() => {
              if (!over) onTrash();
            }}
            className="gap-1.5"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            {t('workbench.files.trash')}
          </Button>
        )}
      </SelectionBar>
      {over && (
        <p role="status" className="px-1 pt-2 text-sm text-destructive">
          {t('workbench.files.over_bulk', { count: bulkMax })}
        </p>
      )}
    </div>
  );
}

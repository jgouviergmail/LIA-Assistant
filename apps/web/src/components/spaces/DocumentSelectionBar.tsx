'use client';

/**
 * The bar above a space's documents while rows are selected (ADR-259): the
 * shared `SelectionBar` with three actions — the selection as one archive (a
 * real link, so the browser handles the download and the cookie rides
 * along), move to another space, and the bulk delete solid red.
 */

import { Download, FolderInput, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { SelectionBar } from '@/components/ui/selection-bar';
import type { PageSelectionState } from '@/lib/selection';

export interface DocumentSelectionBarProps {
  count: number;
  pageState: PageSelectionState;
  /** The archive endpoint carrying the selected ids. */
  archiveHref: string;
  onSelectAll: () => void;
  onClear: () => void;
  onMove: () => void;
  onDelete: () => void;
  deleting: boolean;
}

export function DocumentSelectionBar({
  count,
  pageState,
  archiveHref,
  onSelectAll,
  onClear,
  onMove,
  onDelete,
  deleting,
}: DocumentSelectionBarProps) {
  const { t } = useTranslation();
  return (
    <SelectionBar
      regionLabel={t('spaces.documents.selection_region')}
      countLabel={t('spaces.documents.selected_count', { count })}
      selectAllLabel={t('spaces.documents.select_all')}
      clearLabel={t('spaces.documents.clear_selection')}
      pageState={pageState}
      onSelectAll={onSelectAll}
      onClear={onClear}
    >
      <Button type="button" size="sm" variant="default" asChild>
        <a href={archiveHref} download>
          <Download className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('spaces.documents.download_selected')}
        </a>
      </Button>
      <Button type="button" size="sm" variant="default" onClick={onMove}>
        <FolderInput className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('spaces.documents.move_selected')}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="destructive"
        onClick={() => !deleting && onDelete()}
        aria-disabled={deleting}
        isLoading={deleting}
      >
        <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('spaces.documents.delete_selected')}
      </Button>
    </SelectionBar>
  );
}

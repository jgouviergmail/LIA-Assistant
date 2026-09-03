'use client';

/**
 * The bar above the meetings list while rows are selected (ADR-259): the
 * shared `SelectionBar` with one action, the bulk delete.
 */

import { Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { SelectionBar } from '@/components/ui/selection-bar';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PageSelectionState } from '@/lib/meetings/selection';

interface MeetingSelectionBarProps {
  lng: Language;
  /** Selected rows that are on this page and selectable. */
  count: number;
  pageState: PageSelectionState;
  onSelectAll: () => void;
  onClear: () => void;
  onDelete: () => void;
  deleting: boolean;
}

export function MeetingSelectionBar({
  lng,
  count,
  pageState,
  onSelectAll,
  onClear,
  onDelete,
  deleting,
}: MeetingSelectionBarProps) {
  const { t } = useTranslation(lng);
  return (
    <SelectionBar
      regionLabel={t('meetings.list.selection_region')}
      countLabel={t('meetings.list.selected_count', { count })}
      selectAllLabel={t('meetings.list.select_all_page')}
      clearLabel={t('meetings.list.clear_selection')}
      pageState={pageState}
      onSelectAll={onSelectAll}
      onClear={onClear}
    >
      <Button
        type="button"
        size="sm"
        variant="destructive"
        onClick={() => !deleting && onDelete()}
        aria-disabled={deleting}
        isLoading={deleting}
      >
        <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('meetings.list.delete_selected', { count })}
      </Button>
    </SelectionBar>
  );
}

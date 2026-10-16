'use client';

/**
 * The persistent page-selection bar above the meetings list (ADR-259): the
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
  canSelectAll: boolean;
  pageState: PageSelectionState;
  onSelectAll: () => void;
  onClear: () => void;
  onDelete: () => void;
  deleting: boolean;
}

export function MeetingSelectionBar({
  lng,
  count,
  canSelectAll,
  pageState,
  onSelectAll,
  onClear,
  onDelete,
  deleting,
}: MeetingSelectionBarProps) {
  const { t } = useTranslation(lng);
  return (
    <SelectionBar
      className="[&>label]:h-auto [&>label]:min-h-11 [&>span]:w-full [&>span]:flex-col [&>span>button]:w-full [&_button]:min-h-11 sm:[&>span]:w-auto sm:[&>span]:flex-row sm:[&>span>button]:w-auto"
      showActions={count > 0}
      selectAllDisabled={!canSelectAll}
      regionLabel={t('meetings.list.selection_region')}
      countLabel={
        count > 0
          ? t('meetings.list.selected_count', { count })
          : t('meetings.list.select_all_page')
      }
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
        onClick={() => count > 0 && !deleting && onDelete()}
        aria-disabled={deleting || count === 0}
        className="aria-disabled:opacity-50"
        aria-busy={deleting}
      >
        <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('meetings.list.delete_selected', { count })}
      </Button>
    </SelectionBar>
  );
}

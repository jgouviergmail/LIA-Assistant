'use client';

/**
 * What ticked tasks can become (ADR-369, lot 9): done, not done, deleted after a question, or
 * sent to another list. Each act answers task by task (`useTaskSelection` tells it): what was
 * done leaves the selection, what could not be stays ticked. While an act runs the others wait.
 */
import { Check, RotateCcw, Trash2 } from '@/lib/icons';

import { Button } from '@/components/ui/button';
import { SelectionBar } from '@/components/ui/selection-bar';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PageSelectionState } from '@/lib/selection';
import type { WorkbenchTaskList } from '@/lib/workbench/types';
import { NativeSelect } from '@/components/ui/native-select';

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
  // A guard, not the attribute: `aria-disabled` keeps the focus where it is.
  const guarded = (act: () => void) => () => {
    if (!busy) act();
  };
  return (
    <div className="border-b px-4 py-2">
      <SelectionBar
        regionLabel={t('workbench.tasks.selection_region')}
        countLabel={t('workbench.tasks.selected', { count })}
        selectAllLabel={t('workbench.tasks.select_page')}
        clearLabel={t('workbench.tasks.clear_selection')}
        pageState={pageState}
        onSelectAll={onSelectAll}
        onClear={onClear}
      >
        <Button
          size="sm"
          variant="outline"
          aria-disabled={busy || undefined}
          onClick={guarded(() => onCompleted(true))}
          className="gap-1.5"
        >
          <Check className="h-4 w-4" aria-hidden="true" />
          {t('workbench.tasks.complete_selection')}
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-disabled={busy || undefined}
          onClick={guarded(() => onCompleted(false))}
          className="gap-1.5"
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          {t('workbench.tasks.reopen_selection')}
        </Button>
        {others.length > 0 && (
          <>
            <NativeSelect
              aria-label={t('workbench.tasks.move_to_list')}
              disabled={busy}
              value=""
              onChange={event => {
                if (event.target.value) onMove(event.target.value);
              }}
              className="h-9 w-auto max-w-44 px-2"
            >
              <option value="">{t('workbench.tasks.move_to_list_pick')}</option>
              {others.map(list => (
                <option key={list.id} value={list.id}>
                  {list.title || t('workbench.tasks.untitled')}
                </option>
              ))}
            </NativeSelect>
          </>
        )}
        <Button
          size="sm"
          variant="outline"
          aria-disabled={busy || undefined}
          onClick={guarded(onDelete)}
          className="gap-1.5 text-destructive"
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          {t('common.delete')}
        </Button>
      </SelectionBar>
    </div>
  );
}

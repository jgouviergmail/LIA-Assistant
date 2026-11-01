'use client';

/**
 * MailSelectionBar — acts on the selected messages (ADR-369, mock-up « Main »).
 *
 * Mark read or unread, label (Gmail), move to the trash — each on every
 * selected message, each answered message by message: the screen says what was
 * done and what was not. A selection beyond the published bulk bound is stated
 * and refused before anything is sent (`limits.bulk_max_items`, ADR-184). The
 * trash needs no dialog: a trashed message can be restored in the mailbox.
 */
import { MailCheck, MailOpen, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { SelectionBar } from '@/components/ui/selection-bar';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PageSelectionState } from '@/lib/selection';
import type { MailFolder, MailSummary } from '@/lib/workbench/types';

import { LabelMenu } from './LabelMenu';

/** Which act is on its way, if any. */
export type MailBulkAct = 'read' | 'unread' | 'labels' | 'trash';

export interface MailSelectionBarProps {
  lng: Language;
  selected: readonly MailSummary[];
  pageState: PageSelectionState;
  bulkMax: number;
  /** The person's labels where the provider has labels; undefined elsewhere. */
  labels: readonly MailFolder[] | undefined;
  busy: MailBulkAct | null;
  onSelectAll: () => void;
  onClear: () => void;
  onRead: (read: boolean) => void;
  onLabels: (add: string[], remove: string[]) => void;
  onTrash: () => void;
}

export function MailSelectionBar({
  lng,
  selected,
  pageState,
  bulkMax,
  labels,
  busy,
  onSelectAll,
  onClear,
  onRead,
  onLabels,
  onTrash,
}: MailSelectionBarProps) {
  const { t } = useTranslation(lng);
  const over = selected.length > bulkMax;
  const held = over || busy !== null;
  // A guard, not the attribute: `aria-disabled` keeps the focus where it is.
  const guarded = (act: () => void) => () => {
    if (!held) act();
  };
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
          {t('workbench.mail.mark_read')}
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
          {t('workbench.mail.mark_unread')}
        </Button>
        {labels && (
          <LabelMenu
            lng={lng}
            labels={labels}
            messages={selected}
            busy={held}
            onApply={(add, remove) => onLabels(add, remove)}
          />
        )}
        <Button
          size="sm"
          variant="destructive"
          aria-disabled={held || undefined}
          isLoading={busy === 'trash'}
          onClick={guarded(onTrash)}
          className="gap-1.5"
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.trash')}
        </Button>
      </SelectionBar>
      {over && (
        <p role="status" className="px-1 pt-2 text-sm text-destructive">
          {t('workbench.mail.over_bulk', { count: bulkMax })}
        </p>
      )}
    </div>
  );
}

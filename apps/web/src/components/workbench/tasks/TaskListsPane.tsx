'use client';

/**
 * TaskListsPane — the account's task lists (ADR-369).
 *
 * From `lg`, a named landmark of links beside the tasks (the open list stated
 * with `aria-current`); below, a native select above them — a column of lists
 * has no room on a phone, and a native control is what the keyboard and the
 * screen reader already know. A list count is never drawn: it would be exact
 * only once every task of every list was read (ADR-185). « More lists » reads
 * the provider's next page; « New list » is offered where the provider manages
 * lists (the descriptor says so).
 */
import Link from 'next/link';
import { ListChecks, Plus } from 'lucide-react';
import { useId } from 'react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { WorkbenchTaskList } from '@/lib/workbench/types';
import type { WorkbenchPageState } from '@/hooks/useWorkbenchPage';

import { paneWidth, type WorkbenchPaneState } from '../useWorkbenchPane';

export interface TaskListsPaneProps {
  lng: Language;
  lists: WorkbenchPageState<WorkbenchTaskList>;
  openId: string | null;
  /** The link to a list. */
  hrefOf: (list: WorkbenchTaskList) => string;
  /** Opens a list from the phone's select. */
  onPick: (listId: string) => void;
  /** Opens the « new list » dialog; absent when the provider manages no list. */
  onNewList?: () => void;
  /**
   * A task's detail is open: between `lg` and `xl` three columns would leave
   * the tasks a sliver (measured: ~150 px at 1024), so the lists step aside.
   */
  detailOpen?: boolean;
  /** The column as the person sized it on a large screen (its separator is the tool's). */
  pane?: WorkbenchPaneState;
}

/** The column beside the tasks (from `lg`). */
export function TaskListsColumn({
  lng,
  lists,
  openId,
  hrefOf,
  onNewList,
  detailOpen = false,
  pane,
}: TaskListsPaneProps) {
  const { t } = useTranslation(lng);
  return (
    <nav
      {...pane?.pane}
      aria-label={t('workbench.tasks.lists_title')}
      className={cn(
        'hidden shrink-0 flex-col gap-0.5 border-r p-3',
        paneWidth(pane, 'w-56'),
        detailOpen ? 'xl:flex' : 'lg:flex'
      )}
    >
      <p className="mb-1 flex items-center gap-2 px-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
        <ListChecks className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
        {t('workbench.tasks.lists_title')}
      </p>
      {lists.items.map(list => (
        <Link
          key={list.id}
          href={hrefOf(list)}
          scroll={false}
          aria-current={list.id === openId ? 'page' : undefined}
          className={cn(
            'truncate rounded-md px-2 py-2 text-sm transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            list.id === openId
              ? 'bg-primary/10 font-medium text-primary'
              : 'text-foreground hover:bg-accent hover:text-accent-foreground'
          )}
        >
          {list.title || t('workbench.tasks.untitled')}
        </Link>
      ))}
      {lists.nextToken && (
        <Button
          variant="ghost"
          size="sm"
          isLoading={lists.loadingMore}
          onClick={() => void lists.loadMore()}
        >
          {t('workbench.tasks.more_lists')}
        </Button>
      )}
      {onNewList && (
        <Button variant="ghost" size="sm" className="mt-2 justify-start" onClick={onNewList}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('workbench.tasks.new_list')}
        </Button>
      )}
    </nav>
  );
}

/** The select above the tasks (below `lg`). */
export function TaskListsSelect({ lng, lists, openId, onPick }: TaskListsPaneProps) {
  const { t } = useTranslation(lng);
  const id = useId();
  return (
    <div className="flex flex-wrap items-end gap-2 border-b px-4 py-3 lg:hidden">
      <div className="min-w-0 flex-1 space-y-3">
        <Label htmlFor={id}>{t('workbench.tasks.list_label')}</Label>
        <select
          id={id}
          value={openId ?? ''}
          onChange={event => onPick(event.target.value)}
          className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {lists.items.map(list => (
            <option key={list.id} value={list.id}>
              {list.title || t('workbench.tasks.untitled')}
            </option>
          ))}
        </select>
      </div>
      {lists.nextToken && (
        <Button
          variant="outline"
          size="sm"
          isLoading={lists.loadingMore}
          onClick={() => void lists.loadMore()}
        >
          {t('workbench.tasks.more_lists')}
        </Button>
      )}
    </div>
  );
}

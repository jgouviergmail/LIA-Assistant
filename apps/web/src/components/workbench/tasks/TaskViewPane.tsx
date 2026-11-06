'use client';

/**
 * TaskViewPane — what every list holds for today, overdue or the days ahead (ADR-369, lot 9).
 *
 * A row names its list, its day and opens the task where it lives; ticking it takes it out of
 * the view. The number is exact or absent (ADR-185): a list read in part or not at all takes it
 * away and says so.
 */
import { CalendarCheck } from 'lucide-react';
import Link from 'next/link';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatDay } from '@/lib/workbench/tasks';
import type {
  DueTask,
  DueTasks,
  WorkbenchTaskList,
  WorkbenchTaskView,
} from '@/lib/workbench/types';

export interface TaskViewPaneProps {
  lng: Language;
  view: WorkbenchTaskView;
  read: WorkbenchItemState<DueTasks>;
  lists: readonly WorkbenchTaskList[];
  /** The link to a task, in its list. */
  hrefOf: (task: DueTask) => string;
  onComplete: (task: DueTask) => void;
}

export function TaskViewPane({ lng, view, read, lists, hrefOf, onComplete }: TaskViewPaneProps) {
  const { t } = useTranslation(lng);
  const answer = read.item;
  const whole = answer !== undefined && !answer.truncated && answer.failed.length === 0;
  return (
    <>
      <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
        <h2 className="min-w-0 flex-1 truncate text-base font-semibold text-foreground">
          {t(`workbench.tasks.views.${view}`)}
        </h2>
        {whole && (
          <span className="text-xs text-muted-foreground">
            {t('workbench.tasks.to_do', { count: answer.tasks.length })}
          </span>
        )}
      </div>
      <ViewBody
        lng={lng}
        view={view}
        read={read}
        lists={lists}
        hrefOf={hrefOf}
        onComplete={onComplete}
      />
    </>
  );
}

function ViewBody({ lng, view, read, lists, hrefOf, onComplete }: TaskViewPaneProps) {
  const { t } = useTranslation(lng);
  const answer = read.item;
  if (read.loading) {
    return (
      <div className="space-y-2 p-4">
        {[1, 2, 3].map(index => (
          <Skeleton key={index} className="h-10 w-full" />
        ))}
      </div>
    );
  }
  if (!answer) {
    return (
      <EmptyState
        description={t('workbench.tasks.failed')}
        action={{ label: t('workbench.states.retry'), onClick: () => void read.refresh() }}
      />
    );
  }
  const listName = (id: string) => lists.find(list => list.id === id)?.title;
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {answer.tasks.length === 0 ? (
        <EmptyState icon={CalendarCheck} title={t(`workbench.tasks.view_empty.${view}`)} />
      ) : (
        <ul>
          {answer.tasks.map(task => (
            <ViewRow
              key={`${task.list_id}:${task.id}`}
              lng={lng}
              task={task}
              listName={listName(task.list_id)}
              href={hrefOf(task)}
              onComplete={onComplete}
            />
          ))}
        </ul>
      )}
      {(answer.truncated || answer.failed.length > 0) && (
        <p role="status" className="px-4 pt-3 text-sm text-muted-foreground">
          {t('workbench.tasks.view_partial')}
          <Button
            variant="link"
            size="sm"
            className="ml-2 h-auto p-0"
            onClick={() => void read.refresh()}
          >
            {t('workbench.states.retry')}
          </Button>
        </p>
      )}
    </div>
  );
}

function ViewRow({
  lng,
  task,
  listName,
  href,
  onComplete,
}: {
  lng: Language;
  task: DueTask;
  listName: string | undefined;
  href: string;
  onComplete: (task: DueTask) => void;
}) {
  const { t } = useTranslation(lng);
  const title = task.title || t('workbench.tasks.untitled');
  return (
    <li className="flex items-start gap-3 border-b px-4 py-2.5">
      <Checkbox
        className="mt-0.5"
        checked={false}
        aria-label={t('workbench.tasks.complete', { title })}
        onChange={() => onComplete(task)}
      />
      <Link
        href={href}
        scroll={false}
        className="min-w-0 flex-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="block break-words text-sm text-foreground">{title}</span>
        <span className="mt-1 flex flex-wrap items-center gap-2">
          <Badge variant="outline" size="sm">
            {formatDay(task.due, lng)}
          </Badge>
          {listName && <span className="truncate text-xs text-muted-foreground">{listName}</span>}
        </span>
      </Link>
    </li>
  );
}

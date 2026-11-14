'use client';

/**
 * TaskViewPane — what every list holds, gathered: for today, overdue or the days ahead, the
 * three together in time order (« All », one titled stretch each), or every open task, dated
 * or not (« All tasks ») (ADR-369, lot 9; owner, 2026-11-10).
 *
 * A row names its list in a badge, its day against the account's today, and opens the task
 * BESIDE the view, which stays on screen; ticking it takes it out of the view. The number is
 * exact or absent (ADR-185): a list read in part or not at all takes it away and says so.
 */
import {
  CalendarCheck,
  CalendarClock,
  ListChecks,
  TriangleAlert,
  type LucideIcon,
} from '@/lib/icons';
import Link from 'next/link';
import { useId, type RefObject } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import {
  dueTone,
  timelineSections,
  type TimelinePart,
  type TimelineSection,
} from '@/lib/workbench/tasks';
import type {
  ViewTask,
  ViewTasks,
  WorkbenchTaskList,
  WorkbenchTaskView,
} from '@/lib/workbench/types';

import { TaskDueChip } from './TaskDueChip';
import { TaskListBadge } from './TaskListBadge';

/** The task open beside the view: its id alone would name another list's task. */
export interface OpenViewTask {
  listId: string | null;
  taskId: string;
}

export interface TaskViewPaneProps {
  lng: Language;
  view: WorkbenchTaskView;
  read: WorkbenchItemState<ViewTasks>;
  lists: readonly WorkbenchTaskList[];
  /** Today in the account's zone (`dayIn`). */
  today: string;
  /** The task open beside the view, if any. */
  open: OpenViewTask | null;
  /** The link to a task, in its list, the view kept. */
  hrefOf: (task: ViewTask) => string;
  onComplete: (task: ViewTask) => void;
  /** Hands each task's link to the screen, which gives it the focus back. */
  linkRef: (taskId: string, link: HTMLAnchorElement | null) => void;
  /** The view's title: what takes the focus back when the task that was open left the view. */
  headingRef: RefObject<HTMLHeadingElement | null>;
}

const SECTION_ICONS: Record<TimelinePart, LucideIcon> = {
  overdue: TriangleAlert,
  today: CalendarCheck,
  upcoming: CalendarClock,
};

export function TaskViewPane(props: TaskViewPaneProps) {
  const { lng, view, read, headingRef } = props;
  const { t } = useTranslation(lng);
  const answer = read.item;
  const whole = answer !== undefined && !answer.truncated && answer.failed.length === 0;
  return (
    <>
      <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
        <h2
          ref={headingRef}
          tabIndex={-1}
          className="min-w-0 flex-1 truncate rounded-sm text-base font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {t(`workbench.tasks.views.${view}`)}
        </h2>
        {whole && (
          <span className="text-xs text-muted-foreground">
            {t('workbench.tasks.to_do', { count: answer.tasks.length })}
          </span>
        )}
      </div>
      <ViewBody {...props} whole={whole} />
    </>
  );
}

function ViewBody({ whole, ...props }: TaskViewPaneProps & { whole: boolean }) {
  const { lng, view, read, today } = props;
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
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {answer.tasks.length === 0 && (
        <EmptyState
          icon={view === 'all' ? ListChecks : CalendarCheck}
          title={t(`workbench.tasks.view_empty.${view}`)}
        />
      )}
      {view === 'timeline' ? (
        timelineSections(answer.tasks, today).map(section => (
          <TimelineStretch key={section.part} {...props} section={section} counted={whole} />
        ))
      ) : (
        <ViewRows {...props} tasks={answer.tasks} />
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

/** One stretch of the timeline under its title: what is late, today's, the days ahead. */
function TimelineStretch({
  section,
  counted,
  ...props
}: TaskViewPaneProps & { section: TimelineSection; counted: boolean }) {
  const { t } = useTranslation(props.lng);
  const titleId = useId();
  const Icon = SECTION_ICONS[section.part];
  return (
    <section aria-labelledby={titleId}>
      <h3
        id={titleId}
        className="flex items-center gap-2 border-b bg-muted/40 px-4 py-2 text-xs font-bold uppercase tracking-wider text-muted-foreground"
      >
        <Icon className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
        <span>{t(`workbench.tasks.views.${section.part}`)}</span>{' '}
        {counted && (
          <span className="font-normal normal-case tracking-normal">
            {t('workbench.tasks.to_do', { count: section.tasks.length })}
          </span>
        )}
      </h3>
      <ViewRows {...props} tasks={section.tasks} />
    </section>
  );
}

function ViewRows({ tasks, ...props }: TaskViewPaneProps & { tasks: readonly ViewTask[] }) {
  const { lng, lists, today, open, hrefOf, onComplete, linkRef } = props;
  if (tasks.length === 0) return null;
  return (
    <ul>
      {tasks.map(task => (
        <ViewRow
          key={`${task.list_id}:${task.id}`}
          lng={lng}
          task={task}
          today={today}
          listName={lists.find(list => list.id === task.list_id)?.title}
          open={open !== null && open.taskId === task.id && open.listId === task.list_id}
          href={hrefOf(task)}
          onComplete={onComplete}
          linkRef={linkRef}
        />
      ))}
    </ul>
  );
}

interface ViewRowProps {
  lng: Language;
  task: ViewTask;
  today: string;
  listName: string | undefined;
  open: boolean;
  href: string;
  onComplete: (task: ViewTask) => void;
  linkRef: (taskId: string, link: HTMLAnchorElement | null) => void;
}

function ViewRow({ lng, task, today, listName, open, href, onComplete, linkRef }: ViewRowProps) {
  const { t } = useTranslation(lng);
  const title = task.title || t('workbench.tasks.untitled');
  return (
    <li className={cn('flex items-start gap-3 border-b px-4 py-2.5', open && 'bg-primary/10')}>
      <Checkbox
        className="mt-0.5"
        checked={false}
        aria-label={t('workbench.tasks.complete', { title })}
        onChange={() => onComplete(task)}
      />
      <Link
        ref={link => linkRef(task.id, link)}
        href={href}
        scroll={false}
        aria-current={open ? 'true' : undefined}
        className="min-w-0 flex-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="block break-words text-sm text-foreground">{title}</span>
        {(task.due || listName) && (
          <span className="mt-1 flex flex-wrap items-center gap-2">
            {task.due && (
              <TaskDueChip
                lng={lng}
                due={task.due}
                tone={dueTone({ due: task.due, completed: false }, today)}
              />
            )}
            {listName && <TaskListBadge name={listName} label={t('workbench.tasks.list_label')} />}
          </span>
        )}
      </Link>
    </li>
  );
}

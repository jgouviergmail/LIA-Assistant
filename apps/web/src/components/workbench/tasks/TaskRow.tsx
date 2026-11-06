'use client';

/**
 * TaskRow — one task of the « Tools » list, its subtasks nested under it (ADR-369).
 *
 * The checkbox marks it done or not (named with the task, so a screen reader
 * hears which one); the rest of the row is a LINK to the task's detail (the
 * open task rides the address). A due day reads against the account's today:
 * « Today » and an overdue day are drawn in the warning tone, and an overdue
 * day also SAYS so — colour is never the only carrier. A checkbox whose last
 * change is still on its way takes no second one (`aria-disabled`, guarded in
 * the hook): disabling it would blur it under the keyboard. While the person
 * selects, the tick selects: two checkboxes on a line would read as one.
 */
import Link from 'next/link';
import { CalendarDays } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { dueTone, formatDay, type TaskNode } from '@/lib/workbench/tasks';
import type { WorkbenchTask } from '@/lib/workbench/types';

export interface TaskRowProps {
  lng: Language;
  node: TaskNode;
  /** Today in the account's zone (`dayIn`). */
  today: string;
  /** The open task, if any. */
  openId: string | null;
  /** The tasks whose completion is on its way. */
  pending: ReadonlySet<string>;
  /** The link to a task's detail. */
  hrefOf: (task: WorkbenchTask) => string;
  onToggle: (task: WorkbenchTask, completed: boolean) => void;
  /** Hands each task's link to the screen, which gives it the focus back. */
  linkRef: (taskId: string, link: HTMLAnchorElement | null) => void;
  /** What is ticked, while the person selects. */
  selection?: RowSelection;
}

/** The tasks ticked, and how a task gets ticked. */
export interface RowSelection {
  selected: ReadonlySet<string>;
  onToggle: (task: WorkbenchTask) => void;
}

export function TaskRow({
  lng,
  node,
  today,
  openId,
  pending,
  hrefOf,
  onToggle,
  linkRef,
  selection,
}: TaskRowProps) {
  return (
    <li>
      <TaskLine
        lng={lng}
        task={node.task}
        today={today}
        open={node.task.id === openId}
        busy={pending.has(node.task.id)}
        href={hrefOf(node.task)}
        onToggle={onToggle}
        linkRef={linkRef}
        selection={selection}
      />
      {node.children.length > 0 && (
        <ul className="pl-8">
          {node.children.map(child => (
            <li key={child.id}>
              <TaskLine
                lng={lng}
                task={child}
                today={today}
                open={child.id === openId}
                busy={pending.has(child.id)}
                href={hrefOf(child)}
                onToggle={onToggle}
                linkRef={linkRef}
                selection={selection}
              />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

interface TaskLineProps {
  lng: Language;
  task: WorkbenchTask;
  today: string;
  open: boolean;
  busy: boolean;
  href: string;
  onToggle: (task: WorkbenchTask, completed: boolean) => void;
  linkRef: (taskId: string, link: HTMLAnchorElement | null) => void;
  selection?: RowSelection;
}

function TaskLine({
  lng,
  task,
  today,
  open,
  busy,
  href,
  onToggle,
  linkRef,
  selection,
}: TaskLineProps) {
  const { t } = useTranslation(lng);
  const title = task.title || t('workbench.tasks.untitled');
  const notes = task.notes?.split('\n', 1)[0];
  return (
    <div className={cn('flex items-start gap-3 border-b px-4 py-2.5', open && 'bg-primary/10')}>
      {selection ? (
        <Checkbox
          className="mt-0.5"
          checked={selection.selected.has(task.id)}
          aria-label={t('workbench.tasks.select_task', { title })}
          onChange={() => selection.onToggle(task)}
        />
      ) : (
        <Checkbox
          className="mt-0.5"
          checked={task.completed}
          aria-disabled={busy || undefined}
          aria-label={t(task.completed ? 'workbench.tasks.reopen' : 'workbench.tasks.complete', {
            title,
          })}
          onChange={event => {
            if (!busy) onToggle(task, event.currentTarget.checked);
          }}
        />
      )}
      <Link
        ref={link => linkRef(task.id, link)}
        href={href}
        scroll={false}
        aria-current={open ? 'true' : undefined}
        className="min-w-0 flex-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span
          className={cn(
            'block break-words text-sm',
            task.completed ? 'text-muted-foreground line-through' : 'text-foreground'
          )}
        >
          {title}
        </span>
        {(task.due || notes) && (
          <span className="mt-1 flex flex-wrap items-center gap-2">
            {task.due && <DueChip lng={lng} task={task} today={today} />}
            {notes && <span className="truncate text-xs text-muted-foreground">{notes}</span>}
          </span>
        )}
      </Link>
    </div>
  );
}

/** The day a task is due, read against today. */
function DueChip({ lng, task, today }: { lng: Language; task: WorkbenchTask; today: string }) {
  const { t } = useTranslation(lng);
  const tone = dueTone(task, today);
  const due = task.due ?? '';
  return (
    <Badge variant={tone === 'later' ? 'outline' : 'warning'} size="sm">
      <CalendarDays className="h-3 w-3" aria-hidden="true" />
      {tone === 'today' ? t('workbench.tasks.today') : formatDay(due, lng)}
      {tone === 'overdue' && <span className="sr-only"> {t('workbench.tasks.overdue')}</span>}
    </Badge>
  );
}

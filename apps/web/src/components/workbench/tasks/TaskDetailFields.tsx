'use client';

/**
 * What a task holds beyond its words, each drawn where its provider keeps it (ADR-369, lot 9).
 *
 * To Do keeps steps, an importance, a reminder and a repetition; Google keeps an order. A change
 * leaves when the person makes it. A repetition starts on a due day, so it waits for one, and a
 * pattern the screen has no word for stays named and is only replaced on purpose. A reminder
 * reads and writes on the account's clock, whatever the browser's. Any task can go to another
 * list: on To Do it is a copy, so it keeps what it holds and takes another id.
 */
import { ArrowDown, ArrowUp, X } from 'lucide-react';
import { useId, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { TaskChangeBody } from '@/hooks/useWorkbenchTasks';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { reminderInput, reminderInstant } from '@/lib/workbench/tasks';
import type {
  WorkbenchTask,
  WorkbenchTaskImportance,
  WorkbenchTaskList,
  WorkbenchTaskRepeat,
  WorkbenchTaskStep,
  WorkbenchToolAvailability,
} from '@/lib/workbench/types';

import { TaskQuickAdd } from './TaskQuickAdd';

const FIELD =
  'h-10 w-full rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60';
const IMPORTANCES: readonly WorkbenchTaskImportance[] = ['low', 'normal', 'high'];
const REPEATS: readonly WorkbenchTaskRepeat[] = ['daily', 'weekly', 'monthly', 'yearly'];

export interface TaskStepActs {
  onAdd: (task: WorkbenchTask, title: string, key: string) => Promise<void>;
  onToggle: (task: WorkbenchTask, step: WorkbenchTaskStep) => void;
  onRemove: (task: WorkbenchTask, step: WorkbenchTaskStep) => void;
}

export interface TaskStepsProps extends TaskStepActs {
  lng: Language;
  task: WorkbenchTask;
  tool: WorkbenchToolAvailability;
}

/** A task's own checklist. */
export function TaskSteps({ lng, task, tool, onAdd, onToggle, onRemove }: TaskStepsProps) {
  const { t } = useTranslation(lng);
  if (!tool.features.includes('task_steps')) return null;
  return (
    <section aria-label={t('workbench.tasks.steps_title')} className="space-y-2 border-t pt-4">
      <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
        {t('workbench.tasks.steps_title')}
      </p>
      <ul className="space-y-1">
        {task.steps.map(step => (
          <li key={step.id} className="flex items-start gap-2 text-sm">
            <Checkbox
              className="mt-0.5"
              checked={step.checked}
              aria-label={t(step.checked ? 'workbench.tasks.reopen' : 'workbench.tasks.complete', {
                title: step.title,
              })}
              onChange={() => onToggle(task, step)}
            />
            <span
              className={
                step.checked
                  ? 'min-w-0 flex-1 text-muted-foreground line-through'
                  : 'min-w-0 flex-1'
              }
            >
              {step.title}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              aria-label={t('workbench.tasks.remove_step', { title: step.title })}
              onClick={() => onRemove(task, step)}
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          </li>
        ))}
      </ul>
      <TaskQuickAdd
        lng={lng}
        labelKey="workbench.tasks.new_step"
        placeholderKey="workbench.tasks.new_step_placeholder"
        maxLength={tool.bounds.title_max_chars}
        className="border-b-0 px-0 py-0"
        onAdd={(title, key) => onAdd(task, title, key)}
      />
    </section>
  );
}

export interface TaskDetailsProps {
  lng: Language;
  task: WorkbenchTask;
  /** The account's zone: a reminder reads on its clock. */
  zone: string;
  /** The due day the form holds: a repetition starts on it. */
  due: string;
  onChange: (change: TaskChangeBody) => void;
}

/** How much it matters, when it reminds, how it repeats. */
export function TaskDetails({ lng, task, zone, due, onChange }: TaskDetailsProps) {
  const { t } = useTranslation(lng);
  const importanceId = useId();
  const repeatId = useId();
  const [reminder, setReminder] = useState(() => reminderInput(task.reminder, zone));
  const repeatable = due !== '' || task.repeat !== null;
  const leaveReminder = () => {
    const instant = reminderInstant(reminder, zone);
    if (instant !== task.reminder) onChange({ reminder: instant });
  };
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <Label htmlFor={importanceId}>{t('workbench.tasks.importance')}</Label>
        <select
          id={importanceId}
          className={FIELD}
          value={task.importance ?? 'normal'}
          onChange={event =>
            onChange({ importance: event.target.value as WorkbenchTaskImportance })
          }
        >
          {IMPORTANCES.map(importance => (
            <option key={importance} value={importance}>
              {t(`workbench.tasks.importance_${importance}`)}
            </option>
          ))}
        </select>
      </div>
      <Input
        type="datetime-local"
        label={t('workbench.tasks.reminder')}
        value={reminder}
        onChange={event => setReminder(event.target.value)}
        onBlur={leaveReminder}
      />
      <div className="space-y-1">
        <Label htmlFor={repeatId}>{t('workbench.tasks.repeat')}</Label>
        <select
          id={repeatId}
          className={FIELD}
          disabled={!repeatable}
          value={task.repeat ?? ''}
          onChange={event =>
            onChange({ repeat: (event.target.value || null) as WorkbenchTaskRepeat | null })
          }
        >
          <option value="">{t('workbench.tasks.repeat_none')}</option>
          {REPEATS.map(repeat => (
            <option key={repeat} value={repeat}>
              {t(`workbench.tasks.repeat_${repeat}`)}
            </option>
          ))}
          {task.repeat === 'custom' && (
            <option value="custom" disabled>
              {t('workbench.tasks.repeat_custom')}
            </option>
          )}
        </select>
        {!repeatable && (
          <p className="text-xs text-muted-foreground">{t('workbench.tasks.repeat_needs_due')}</p>
        )}
      </div>
    </div>
  );
}

/** Its list, the account's, and how it gets to another. */
export interface TaskMoves {
  listId: string;
  lists: readonly WorkbenchTaskList[];
  busy: boolean;
  onMove: (destination: string) => void;
}

export interface TaskMoveFieldProps extends TaskMoves {
  lng: Language;
}

/** Another list for the task; a single list has nowhere to send it. */
export function TaskMoveField({ lng, listId, lists, busy, onMove }: TaskMoveFieldProps) {
  const { t } = useTranslation(lng);
  const id = useId();
  const others = lists.filter(list => list.id !== listId);
  if (others.length === 0) return null;
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{t('workbench.tasks.move_to_list')}</Label>
      <select
        id={id}
        className={FIELD}
        disabled={busy}
        value=""
        onChange={event => {
          if (event.target.value) onMove(event.target.value);
        }}
      >
        <option value="">{t('workbench.tasks.move_to_list_pick')}</option>
        {others.map(list => (
          <option key={list.id} value={list.id}>
            {list.title || t('workbench.tasks.untitled')}
          </option>
        ))}
      </select>
    </div>
  );
}

/** One place up or down; absent at either end. */
export interface TaskOrderActs {
  up?: () => void;
  down?: () => void;
}

export interface TaskOrderProps extends TaskOrderActs {
  lng: Language;
}

/** Up and down among its siblings: what a keyboard and a single finger can do. */
export function TaskOrder({ lng, up, down }: TaskOrderProps) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-disabled={!up || undefined}
        onClick={() => up?.()}
      >
        <ArrowUp className="h-4 w-4" aria-hidden="true" />
        {t('workbench.tasks.move_up')}
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-disabled={!down || undefined}
        onClick={() => down?.()}
      >
        <ArrowDown className="h-4 w-4" aria-hidden="true" />
        {t('workbench.tasks.move_down')}
      </Button>
    </div>
  );
}

export interface TaskExtrasProps {
  lng: Language;
  task: WorkbenchTask;
  tool: WorkbenchToolAvailability;
  zone?: string;
  /** The due day the form holds. */
  due: string;
  moves?: TaskMoves;
  order?: TaskOrderActs;
  onChange: (change: TaskChangeBody) => void;
}

/** What the form holds beyond the words and the day, as far as the provider keeps it. */
export function TaskExtras({
  lng,
  task,
  tool,
  zone = 'UTC',
  due,
  moves,
  order,
  onChange,
}: TaskExtrasProps) {
  return (
    <>
      {tool.features.includes('task_details') && (
        <TaskDetails lng={lng} task={task} zone={zone} due={due} onChange={onChange} />
      )}
      {moves && <TaskMoveField lng={lng} {...moves} />}
      {tool.features.includes('task_order') && order && <TaskOrder lng={lng} {...order} />}
    </>
  );
}

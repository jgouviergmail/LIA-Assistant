'use client';

/**
 * TaskEditor — one task's detail, edited by hand (ADR-369).
 *
 * Only what changed is sent (a field left out is kept by the API); emptying the
 * due date REMOVES it (`due: null`). What is written is saved when the person
 * leaves a field or picks a date, and « Save » stays for those who press it. A
 * provider that keeps a date without a time says so under the field; today,
 * tomorrow and next week are a tap away. Deleting asks first — a deleted task cannot be
 * brought back from here. Where the provider has subtasks, a top-level task
 * lists them and takes a new one; what else it keeps is drawn where it keeps it
 * (`TaskDetailFields`). From `lg` the detail stands beside the list and closes
 * with a button; below, it replaces the list and says where it goes back to. Its acts
 * stand in its bar, « Save » submitting the form from there.
 */
import { Check, RotateCcw, Save, Trash2 } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { OutboundLink } from '@/components/ui/linked-text';
import { Textarea } from '@/components/ui/textarea';
import type { TaskChangeBody } from '@/hooks/useWorkbenchTasks';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { linksOf } from '@/lib/text-links';
import { cn } from '@/lib/utils';
import { addDays } from '@/lib/workbench/calendar/zoned';
import type { WorkbenchTask, WorkbenchToolAvailability } from '@/lib/workbench/types';

import { FieldAssist } from '../assist/FieldAssist';
import { askAct, DetailBar, type AssistOffer } from '../DetailBar';
import { paneWidth, type WorkbenchPaneState } from '../useWorkbenchPane';
import {
  TaskExtras,
  TaskSteps,
  type TaskMoves,
  type TaskOrderActs,
  type TaskStepActs,
} from './TaskDetailFields';
import { TaskQuickAdd } from './TaskQuickAdd';
import { useToolConfirm } from '../ToolForm';

export interface TaskEditorProps {
  lng: Language;
  task: WorkbenchTask;
  /** Its subtasks on screen. */
  subtasks: readonly WorkbenchTask[];
  /** The tasks tool's provider: its gestures and bounds. */
  tool: WorkbenchToolAvailability;
  pending: ReadonlySet<string>;
  onSave: (task: WorkbenchTask, change: TaskChangeBody) => Promise<void>;
  onToggle: (task: WorkbenchTask, completed: boolean) => void;
  onDelete: (task: WorkbenchTask) => Promise<void>;
  onAddSubtask: (parent: WorkbenchTask, title: string, key: string) => Promise<void>;
  onClose: () => void;
  /** Below `lg` the detail REPLACES the list: it takes the focus the hidden row held. */
  focusOnOpen: boolean;
  /** The account's day (`dayIn`). */
  today: string;
  /** Takes the task to LIA. */
  onAsk: (task: WorkbenchTask) => void;
  /** What LIA can do on it, under the question's icon. */
  assist?: AssistOffer;
  /** What LIA answered, first in the detail. */
  assistPanel?: ReactNode;
  /** The detail as the person sized it on a large screen (its separator is the tool's). */
  pane?: WorkbenchPaneState;
  /** The account's zone: a reminder reads on its clock. */
  zone?: string;
  /** Where the task can go, when the screen knows. */
  moves?: TaskMoves;
  /** What changes its steps, where its provider keeps some. */
  steps?: TaskStepActs;
  /** Takes it one place up or down; absent at either end. */
  order?: TaskOrderActs;
}

/** The dates at hand: their words and how far from today. */
const QUICK_DUES: readonly (readonly [string, number])[] = [
  ['workbench.tasks.due_today', 0],
  ['workbench.tasks.due_tomorrow', 1],
  ['workbench.tasks.due_next_week', 7],
];

interface TaskForm {
  title: string;
  notes: string;
  due: string;
}

/** What the form changes, and nothing else. */
function changeOf(task: WorkbenchTask, form: TaskForm): TaskChangeBody {
  const change: TaskChangeBody = {};
  if (form.title.trim() !== task.title) change.title = form.title.trim();
  if (form.notes !== (task.notes ?? '')) change.notes = form.notes;
  if (form.due !== (task.due ?? '')) change.due = form.due || null;
  return change;
}

function sameForm(one: TaskForm, other: TaskForm): boolean {
  return one.title === other.title && one.notes === other.notes && one.due === other.due;
}

export function TaskEditor({
  lng,
  task,
  subtasks,
  tool,
  pending,
  onSave,
  onToggle,
  onDelete,
  onAddSubtask,
  onClose,
  focusOnOpen,
  today,
  onAsk,
  assist,
  assistPanel,
  pane,
  zone,
  moves,
  steps,
  order,
}: TaskEditorProps) {
  const { t } = useTranslation(lng);
  const back = useRef<HTMLButtonElement>(null);
  const formId = useId();
  const { confirm, confirmDialog } = useToolConfirm();
  const [form, setForm] = useState<TaskForm>({
    title: task.title,
    notes: task.notes ?? '',
    due: task.due ?? '',
  });
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  // Set synchronously: leaving a field by pressing « Save » asks twice in one gesture.
  const saving = useRef(false);
  // What was asked while a save ran: it leaves after it, so nothing shown stays unsaved.
  const waiting = useRef<TaskForm | null>(null);
  const titleMissing = form.title.trim() === '';
  const links = useMemo(() => linksOf(form.notes), [form.notes]);
  const hasSubtasks = tool.features.includes('subtasks') && !task.parent;

  useEffect(() => {
    if (focusOnOpen) back.current?.focus({ preventScroll: true });
  }, [focusOnOpen]);

  const commit = async (written: TaskForm): Promise<void> => {
    const change = changeOf(task, written);
    if (written.title.trim() === '' || Object.keys(change).length === 0) return;
    if (saving.current) {
      waiting.current = written;
      return;
    }
    saving.current = true;
    setBusy(true);
    setSaved(false);
    try {
      await onSave(task, change);
      setSaved(true);
    } catch {
      // Said by the caller; what was typed stays.
    } finally {
      saving.current = false;
      setBusy(false);
    }
    const next = waiting.current;
    waiting.current = null;
    if (next && !sameForm(next, written)) await commit(next);
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    await commit(form);
  };
  const pickDue = (due: string) => {
    const written = { ...form, due };
    setForm(written);
    void commit(written);
  };

  const remove = async () => {
    const confirmed = await confirm({
      title: t('workbench.tasks.delete_task_title', { title: task.title }),
      description: t('workbench.tasks.delete_task_description'),
      confirmLabel: t('common.delete'),
    });
    if (confirmed) await onDelete(task);
  };

  return (
    <aside
      {...pane?.pane}
      aria-label={t('workbench.tasks.detail_title')}
      className={cn(
        'flex min-h-0 w-full flex-col lg:shrink-0 lg:border-l',
        paneWidth(pane, 'lg:w-[22rem]')
      )}
    >
      <DetailBar
        lng={lng}
        closeLabel={t('workbench.tasks.close_detail')}
        backLabel={t('workbench.tools.tasks.label')}
        onClose={onClose}
        closeRef={back}
        acts={[
          { label: t('common.save'), icon: Save, form: formId, busy },
          {
            label: t(
              task.completed ? 'workbench.tasks.reopen_action' : 'workbench.tasks.mark_done'
            ),
            icon: task.completed ? RotateCcw : Check,
            held: pending.has(task.id),
            onSelect: () => onToggle(task, !task.completed),
          },
          {
            label: t('common.delete'),
            icon: Trash2,
            danger: true,
            onSelect: () => void remove(),
          },
          askAct(t('workbench.ask.label'), () => onAsk(task), assist),
        ]}
      />
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
        {assistPanel}
        <form id={formId} onSubmit={save} className="space-y-4">
          <Input
            label={t('workbench.tasks.title')}
            value={form.title}
            maxLength={tool.bounds.title_max_chars}
            error={titleMissing ? t('workbench.tasks.title_required') : undefined}
            onChange={event => setForm(previous => ({ ...previous, title: event.target.value }))}
            onBlur={() => void commit(form)}
          />
          <Textarea
            label={t('workbench.tasks.notes')}
            labelEnd={
              <FieldAssist
                lng={lng}
                kind="task_notes"
                value={form.notes}
                onChange={notes => {
                  const written = { ...form, notes };
                  setForm(written);
                  void commit(written);
                }}
              />
            }
            value={form.notes}
            maxLength={tool.bounds.notes_max_chars}
            rows={4}
            onChange={event => setForm(previous => ({ ...previous, notes: event.target.value }))}
            onBlur={() => void commit(form)}
          />
          {links.length > 0 && (
            <ul aria-label={t('workbench.tasks.notes_links')} className="space-y-1 text-sm">
              {links.map((link, index) => (
                <li key={index}>
                  <OutboundLink link={link} />
                </li>
              ))}
            </ul>
          )}
          <div className="space-y-1">
            <Input
              type="date"
              label={t('workbench.tasks.due')}
              value={form.due}
              onChange={event => setForm(previous => ({ ...previous, due: event.target.value }))}
              onBlur={() => void commit(form)}
            />
            <div className="flex flex-wrap gap-1.5 pt-1">
              {QUICK_DUES.map(([key, days]) => (
                <Button
                  key={key}
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 px-2.5 text-xs"
                  onClick={() => pickDue(addDays(today, days))}
                >
                  {t(key)}
                </Button>
              ))}
              {form.due && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2.5 text-xs"
                  onClick={() => pickDue('')}
                >
                  {t('workbench.tasks.due_none')}
                </Button>
              )}
            </div>
            {tool.features.includes('due_date_only') && (
              <p className="text-xs text-muted-foreground">{t('workbench.tasks.due_date_only')}</p>
            )}
          </div>
          <TaskExtras
            lng={lng}
            task={task}
            tool={tool}
            zone={zone}
            due={form.due}
            moves={moves}
            order={order}
            onChange={change => void onSave(task, change).catch(() => undefined)}
          />
          <p role="status" className="text-xs text-muted-foreground empty:-mt-4">
            {saved && t('workbench.tasks.saved')}
          </p>
        </form>
        {steps && <TaskSteps lng={lng} task={task} tool={tool} {...steps} />}
        {hasSubtasks && (
          <section
            aria-label={t('workbench.tasks.subtasks_title')}
            className="space-y-2 border-t pt-4"
          >
            <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              {t('workbench.tasks.subtasks_title')}
            </p>
            <ul className="space-y-1">
              {subtasks.map(subtask => (
                <li key={subtask.id} className="flex items-start gap-2 text-sm">
                  <Checkbox
                    className="mt-0.5"
                    checked={subtask.completed}
                    aria-disabled={pending.has(subtask.id) || undefined}
                    aria-label={t(
                      subtask.completed ? 'workbench.tasks.reopen' : 'workbench.tasks.complete',
                      { title: subtask.title }
                    )}
                    onChange={event => {
                      if (!pending.has(subtask.id)) onToggle(subtask, event.currentTarget.checked);
                    }}
                  />
                  <span className={subtask.completed ? 'text-muted-foreground line-through' : ''}>
                    {subtask.title || t('workbench.tasks.untitled')}
                  </span>
                </li>
              ))}
            </ul>
            <TaskQuickAdd
              lng={lng}
              labelKey="workbench.tasks.new_subtask"
              placeholderKey="workbench.tasks.new_subtask_placeholder"
              maxLength={tool.bounds.title_max_chars}
              className="border-b-0 px-0 py-0"
              onAdd={(title, key) => onAddSubtask(task, title, key)}
            />
          </section>
        )}
      </div>
      {confirmDialog}
    </aside>
  );
}

'use client';

/**
 * TaskEditor — one task's detail, edited by hand (ADR-369).
 *
 * Only what changed is sent (a field left out is kept by the API); emptying the
 * due date REMOVES it (`due: null`). A provider that keeps a date without a
 * time says so under the field. Deleting asks first — a deleted task cannot be
 * brought back from here. Where the provider has subtasks, a top-level task
 * lists them and takes a new one. From `lg` the detail stands beside the list
 * and closes with a button; below, it replaces the list and leads back to it.
 */
import { ArrowLeft, Check, RotateCcw, Save, Trash2, X } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useConfirm } from '@/components/ui/use-confirm';
import type { TaskChangeBody } from '@/hooks/useWorkbenchTasks';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { WorkbenchTask, WorkbenchToolAvailability } from '@/lib/workbench/types';

import { paneWidth, type WorkbenchPaneState } from '../useWorkbenchPane';
import { TaskQuickAdd } from './TaskQuickAdd';

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
  /** The detail as the person sized it on a large screen (its separator is the tool's). */
  pane?: WorkbenchPaneState;
}

/** What the form changes, and nothing else. */
function changeOf(
  task: WorkbenchTask,
  form: { title: string; notes: string; due: string }
): TaskChangeBody {
  const change: TaskChangeBody = {};
  if (form.title.trim() !== task.title) change.title = form.title.trim();
  if (form.notes !== (task.notes ?? '')) change.notes = form.notes;
  if (form.due !== (task.due ?? '')) change.due = form.due || null;
  return change;
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
  pane,
}: TaskEditorProps) {
  const { t } = useTranslation(lng);
  const back = useRef<HTMLButtonElement>(null);
  const { confirm, confirmDialog } = useConfirm();
  const [form, setForm] = useState({
    title: task.title,
    notes: task.notes ?? '',
    due: task.due ?? '',
  });
  const [busy, setBusy] = useState(false);
  const titleMissing = form.title.trim() === '';
  const hasSubtasks = tool.features.includes('subtasks') && !task.parent;

  useEffect(() => {
    if (focusOnOpen) back.current?.focus({ preventScroll: true });
  }, [focusOnOpen]);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const change = changeOf(task, form);
    if (titleMissing || busy || Object.keys(change).length === 0) return;
    setBusy(true);
    try {
      await onSave(task, change);
    } catch {
      // Said by the caller; what was typed stays.
    } finally {
      setBusy(false);
    }
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
        'flex w-full flex-col gap-4 p-4 lg:shrink-0 lg:border-l',
        paneWidth(pane, 'lg:w-[22rem]')
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <Button ref={back} variant="ghost" size="sm" className="lg:hidden" onClick={onClose}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          {t('workbench.tasks.back_to_list')}
        </Button>
        <p className="hidden text-xs font-bold uppercase tracking-wider text-muted-foreground lg:block">
          {t('workbench.tasks.detail_title')}
        </p>
        <Button
          variant="ghost"
          size="icon"
          className="hidden lg:inline-flex"
          aria-label={t('workbench.tasks.close_detail')}
          onClick={onClose}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      <form onSubmit={save} className="space-y-4">
        <Input
          label={t('workbench.tasks.title')}
          value={form.title}
          maxLength={tool.bounds.title_max_chars}
          error={titleMissing ? t('workbench.tasks.title_required') : undefined}
          onChange={event => setForm(previous => ({ ...previous, title: event.target.value }))}
        />
        <Textarea
          label={t('workbench.tasks.notes')}
          value={form.notes}
          maxLength={tool.bounds.notes_max_chars}
          rows={4}
          onChange={event => setForm(previous => ({ ...previous, notes: event.target.value }))}
        />
        <div className="space-y-1">
          <Input
            type="date"
            label={t('workbench.tasks.due')}
            value={form.due}
            onChange={event => setForm(previous => ({ ...previous, due: event.target.value }))}
          />
          {tool.features.includes('due_date_only') && (
            <p className="text-xs text-muted-foreground">{t('workbench.tasks.due_date_only')}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2 border-t pt-4">
          <Button type="submit" size="sm" isLoading={busy}>
            <Save className="h-4 w-4" aria-hidden="true" />
            {t('common.save')}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-disabled={pending.has(task.id) || undefined}
            onClick={() => {
              if (!pending.has(task.id)) onToggle(task, !task.completed);
            }}
          >
            {task.completed ? (
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Check className="h-4 w-4" aria-hidden="true" />
            )}
            {t(task.completed ? 'workbench.tasks.reopen_action' : 'workbench.tasks.mark_done')}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-destructive"
            onClick={() => void remove()}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            {t('common.delete')}
          </Button>
        </div>
      </form>
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
      {confirmDialog}
    </aside>
  );
}

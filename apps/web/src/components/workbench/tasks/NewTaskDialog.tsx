'use client';

/**
 * NewTaskDialog — a task another tool handed over, reviewed whole before it exists (owner,
 * 2026-11-07).
 *
 * Every value LIA read stands in the form: the title, the notes, the day, the list it named (else
 * the open one), and where the provider keeps them the importance, the reminder and the
 * repetition. Nothing exists until « Add »; one key covers the submission until the task is made,
 * so a second press after a lost answer is told what became of the first. A refusal keeps the form.
 */
import { useRef, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { NativeSelect } from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';
import type { NewTaskBody, TaskChangeBody } from '@/hooks/useWorkbenchTasks';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn, generateUUID } from '@/lib/utils';
import type { WorkbenchTaskList, WorkbenchToolAvailability } from '@/lib/workbench/types';

import { FieldAssist } from '../assist/FieldAssist';
import { CancelButton, TOOL_FORM_SCREEN, ToolActions, ToolDialogHeader } from '../ToolForm';
import { TaskDetails, type TaskDetailValues } from './TaskDetailFields';
import { TaskDueField } from './TaskDueField';

/** What the form opens on. */
export interface NewTaskFields {
  title: string;
  notes: string;
  /** `YYYY-MM-DD`, or empty. */
  due: string;
  /** A list as LIA named it: the open list stands where none of the person's has that name. */
  listName?: string | null;
  /** What LIA read of how much it matters. */
  importance?: 'high' | null;
}

export interface NewTaskDialogProps {
  lng: Language;
  /** The tasks tool's provider: its gestures and bounds. */
  tool: WorkbenchToolAvailability;
  lists: readonly WorkbenchTaskList[];
  /** The list open on screen. */
  listId: string;
  /** The account's day, `YYYY-MM-DD`. */
  today: string;
  /** The account's zone: a reminder reads on its clock. */
  zone: string;
  initial: NewTaskFields;
  /** Makes the task; rejects when refused, the caller saying why. */
  onCreate: (body: NewTaskBody) => Promise<void>;
  onClose: () => void;
}

/** The list a name points to, compared as a person reads it; else the open list. */
function listNamed(
  lists: readonly WorkbenchTaskList[],
  name: string | null | undefined,
  open: string
) {
  const wanted = name?.trim().toLocaleLowerCase();
  if (!wanted) return open;
  return lists.find(list => list.title.trim().toLocaleLowerCase() === wanted)?.id ?? open;
}

/** What is sent: the provider's own fields only where it keeps them, a repetition with a day. */
function bodyOf(
  form: NewTaskFields & { listId: string },
  details: TaskDetailValues,
  keepsDetails: boolean,
  key: string
): NewTaskBody {
  const body: NewTaskBody = {
    title: form.title.trim(),
    list_id: form.listId,
    idempotency_key: key,
    ...(form.notes.trim() ? { notes: form.notes } : {}),
    ...(form.due ? { due: form.due } : {}),
  };
  if (!keepsDetails) return body;
  return {
    ...body,
    ...(details.importance ? { importance: details.importance } : {}),
    ...(details.reminder ? { reminder: details.reminder } : {}),
    ...(details.repeat && details.repeat !== 'custom' && form.due
      ? { repeat: details.repeat }
      : {}),
  };
}

export function NewTaskDialog({
  lng,
  tool,
  lists,
  listId,
  today,
  zone,
  initial,
  onCreate,
  onClose,
}: NewTaskDialogProps) {
  const { t } = useTranslation(lng);
  const [form, setForm] = useState(() => ({
    ...initial,
    listId: listNamed(lists, initial.listName, listId),
  }));
  const [details, setDetails] = useState<TaskDetailValues>(() => ({
    importance: initial.importance ?? null,
    reminder: null,
    repeat: null,
  }));
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  // Minted once, kept until the task is made: a press after a lost answer is the same act.
  const [key] = useState(() => generateUUID());
  const keepsDetails = tool.features.includes('task_details');
  const titleMissing = form.title.trim() === '';
  const set = (change: Partial<typeof form>) => setForm(current => ({ ...current, ...change }));
  const changeDetails = (change: TaskChangeBody) =>
    setDetails(current => ({
      importance: change.importance ?? current.importance,
      reminder: 'reminder' in change ? (change.reminder ?? null) : current.reminder,
      repeat: 'repeat' in change ? (change.repeat ?? null) : current.repeat,
    }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting.current || titleMissing) return;
    submitting.current = true;
    setBusy(true);
    try {
      await onCreate(bodyOf(form, details, keepsDetails, key));
      onClose();
    } catch {
      // Said by the caller; the form and its key stay for a second try.
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={open => !open && !busy && onClose()}>
      <DialogContent aria-describedby={undefined} className={cn(TOOL_FORM_SCREEN, 'sm:max-w-xl')}>
        <ToolDialogHeader>
          <DialogTitle>{t('workbench.tasks.new_task')}</DialogTitle>
        </ToolDialogHeader>
        <form className="space-y-4" onSubmit={submit}>
          <Input
            label={t('workbench.tasks.title')}
            value={form.title}
            maxLength={tool.bounds.title_max_chars}
            error={titleMissing ? t('workbench.tasks.title_required') : undefined}
            onChange={event => set({ title: event.target.value })}
          />
          <Textarea
            label={t('workbench.tasks.notes')}
            labelEnd={
              <FieldAssist
                lng={lng}
                kind="task_notes"
                value={form.notes}
                onChange={notes => set({ notes })}
              />
            }
            value={form.notes}
            maxLength={tool.bounds.notes_max_chars}
            rows={5}
            onChange={event => set({ notes: event.target.value })}
          />
          <TaskDueField
            lng={lng}
            value={form.due}
            today={today}
            dateOnly={tool.features.includes('due_date_only')}
            onType={due => set({ due })}
            onPick={due => set({ due })}
          />
          {lists.length > 1 && (
            <NativeSelect
              label={t('workbench.tasks.list_label')}
              value={form.listId}
              onChange={event => set({ listId: event.target.value })}
            >
              {lists.map(list => (
                <option key={list.id} value={list.id}>
                  {list.title || t('workbench.tasks.untitled')}
                </option>
              ))}
            </NativeSelect>
          )}
          {keepsDetails && (
            <TaskDetails
              lng={lng}
              details={details}
              zone={zone}
              due={form.due}
              onChange={changeDetails}
              live
            />
          )}
          <ToolActions>
            <CancelButton
              lng={lng}
              aria-disabled={busy || undefined}
              onClick={() => {
                if (!busy) onClose();
              }}
            />
            <Button type="submit" isLoading={busy} aria-disabled={titleMissing || undefined}>
              {t('workbench.tasks.add')}
            </Button>
          </ToolActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}

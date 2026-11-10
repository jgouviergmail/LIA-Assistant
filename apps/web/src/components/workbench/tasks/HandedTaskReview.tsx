'use client';

/**
 * HandedTaskReview — what another tool handed the tasks tool, reviewed whole before it exists
 * (owner, 2026-11-07).
 *
 * The handoff is taken once the lists are read: the form it opens names where the task goes, so a
 * hand-over that arrives with the screen waits for them rather than landing in a list chosen
 * blind. A task made in another list than the open one says where it went.
 */
import { useState } from 'react';
import { toast } from 'sonner';

import type { NewTaskBody } from '@/hooks/useWorkbenchTasks';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorkbenchHandoff } from '@/lib/workbench/handoff';
import type { WorkbenchTaskList, WorkbenchToolAvailability } from '@/lib/workbench/types';

import { useHandoff } from '@/hooks/useHandoff';
import { NewTaskDialog } from './NewTaskDialog';

/** What another tool handed over, for the person to review. */
type HandedTask = Omit<Extract<WorkbenchHandoff, { kind: 'task' }>, 'kind'>;

export interface HandedTaskReviewProps {
  lng: Language;
  /** The tasks tool's provider: its gestures and bounds. */
  tool: WorkbenchToolAvailability;
  lists: readonly WorkbenchTaskList[];
  /** The list open on screen; null while the lists are read. */
  listId: string | null;
  /** The account's day, `YYYY-MM-DD`. */
  today: string;
  /** The account's zone, when it has one. */
  timezone: string | undefined;
  /** Makes the task; rejects when refused, having said why. */
  addTask: (body: NewTaskBody) => Promise<void>;
}

export function HandedTaskReview({
  lng,
  tool,
  lists,
  listId,
  today,
  timezone,
  addTask,
}: HandedTaskReviewProps) {
  const { t } = useTranslation(lng);
  const [handed, setHanded] = useState<HandedTask | null>(null);
  useHandoff(
    'task',
    listId !== null && lists.some(list => list.id === listId),
    setHanded,
    handed !== null
  );
  if (!handed || !listId) return null;
  return (
    <NewTaskDialog
      lng={lng}
      tool={tool}
      lists={lists}
      listId={listId}
      today={today}
      zone={timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone}
      initial={{
        title: handed.title,
        notes: handed.notes,
        due: handed.due ?? '',
        listName: handed.list_name,
        importance: handed.importance,
      }}
      onCreate={async body => {
        await addTask(body);
        const elsewhere = lists.find(list => list.id === body.list_id);
        if (elsewhere && elsewhere.id !== listId) {
          toast.success(t('workbench.tasks.added_to', { list: elsewhere.title }));
        }
      }}
      onClose={() => setHanded(null)}
    />
  );
}

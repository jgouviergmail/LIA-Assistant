'use client';

/**
 * What LIA can do on a task (ADR-372): the list under its bar's last icon, the steps it proposes,
 * and the sentence it reads inside the quick add. Nothing exists until the person says so.
 * A slot can be blocked for it in the calendar (2026-11-07), the person's own act, no model: the
 * editor opens on its title and notes, on its day at nine when that day is still to come.
 */
import { CalendarClock, ListChecks } from '@/lib/icons';
import { useState, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { generateUUID } from '@/lib/utils';
import {
  ASSIST_PATHS,
  type ProposedTask,
  type StepsAnswer,
  type TaskAnswer,
} from '@/lib/workbench/assist';
import { datedDay } from '@/lib/workbench/calendar/format';
import type { WorkbenchHandoff } from '@/lib/workbench/handoff';
import { dayIn } from '@/lib/workbench/tasks';
import type { WorkbenchTask } from '@/lib/workbench/types';
import type { LLMUsage } from '@/types/llm-usage';

import type { AssistOffer, DetailDeed } from '../DetailBar';
import type { QuickAddAssist } from '../tasks/TaskQuickAdd';
import { useToolBridges } from '../useToolBridges';
import { useAssistBounds } from '../WorkbenchShell';
import { AssistStars } from '@/components/selection-assist/AssistStars';
import { AssistPanel } from './AssistPanel';
import { confideLine, readyLine, remindLine, type Say } from './lines';
import { tellCost, useToldFailure } from './tellings';
import { useAssistCall, useLatest } from '@/hooks/useAssistCall';

export interface TaskAssist extends AssistOffer {
  /** The answer, first in the detail. */
  panel: ReactNode;
}

/** Adds one step to the open task, under its own key. */
export type AddStep = (title: string, key: string) => Promise<void>;

/** The hour a slot blocked on a day still to come starts at, as a new event's does. */
const SLOT_HOUR = '09:00';

/**
 * The event a slot for a task opens on: its day at nine when that day is still to come, else today
 * at the calendar's next hour.
 */
function slotFor(task: WorkbenchTask, today: string): WorkbenchHandoff {
  const description = task.notes ?? '';
  if (!task.due || task.due <= today) {
    return { kind: 'event', summary: task.title, description };
  }
  return {
    kind: 'event',
    summary: task.title,
    description,
    proposal: {
      summary: task.title,
      start_date: task.due,
      start_time: SLOT_HOUR,
      end_date: null,
      end_time: null,
      all_day: false,
      location: '',
      description,
      attendees: [],
      repeat: 'none',
      conference: false,
    },
  };
}

/**
 * @param lng - The reader's language.
 * @param task - The task open.
 * @param addStep - Adds a step where its provider keeps some.
 * @param zone - The account's zone, which « today » is read in.
 * @returns The offer of its bar, and the answer's place.
 */
export function useTaskAssist(
  lng: Language,
  task: WorkbenchTask,
  addStep?: AddStep,
  zone?: string
): TaskAssist {
  const { t } = useTranslation(lng);
  const { ask, remind, confide, offers, go } = useToolBridges(lng);
  const bounds = useAssistBounds();
  const steps = useAssistCall<StepsAnswer>(task.id);
  const title = task.title || t('workbench.tasks.untitled');
  const offered = bounds !== null && addStep !== undefined && task.title !== '';
  return {
    lines: [
      ...(offered
        ? [
            {
              label: t('workbench.assist.tasks.steps'),
              icon: ListChecks,
              onSelect: () => {
                void steps.run(ASSIST_PATHS.taskSteps, {
                  title: task.title.slice(0, bounds.instructionMax),
                  notes: task.notes?.slice(0, bounds.textMax) || null,
                });
              },
            },
          ]
        : []),
      ...slotLine(t, task, offers('event'), () => go(slotFor(task, dayIn(zone, new Date())))),
      remindLine(t, title, remind),
      ...confideLine(t, title, task.notes ?? '', confide),
      readyLine(t, 'task', { title }, ask),
    ],
    busy: steps.state.status === 'running',
    panel: addStep && (
      <AssistPanel lng={lng} title={t('workbench.assist.tasks.steps_title')} call={steps}>
        {answer => (
          <ProposedSteps lng={lng} steps={answer.steps} addStep={addStep} onDone={steps.stop} />
        )}
      </AssistPanel>
    ),
  };
}

/** A slot in the calendar, for a task still to do with a title, where a calendar is ready. */
function slotLine(
  t: Say,
  task: WorkbenchTask,
  ready: boolean,
  onSelect: () => void
): readonly DetailDeed[] {
  if (!ready || task.completed || !task.title) return [];
  return [{ label: t('workbench.assist.tasks.block_slot'), icon: CalendarClock, onSelect }];
}

/**
 * The steps proposed, and the press that adds them, one by one, in order. Each has its own key for
 * as long as it stands here, and one that was added leaves the list: a second press after a failure
 * goes on from where it stopped, and adds nothing twice.
 */
function ProposedSteps({
  lng,
  steps,
  addStep,
  onDone,
}: {
  lng: Language;
  steps: readonly string[];
  addStep: AddStep;
  onDone: () => void;
}) {
  const { t } = useTranslation(lng);
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(0);
  const [keys] = useState(() => steps.map(() => generateUUID()));
  const add = async () => {
    setAdding(true);
    try {
      for (let index = added; index < steps.length; index += 1) {
        await addStep(steps[index], keys[index]);
        setAdded(index + 1);
      }
      onDone();
    } catch {
      // Said by the caller; what is left stays proposed.
      setAdding(false);
    }
  };
  return (
    <div className="space-y-2">
      <ol className="list-decimal space-y-0.5 pl-5" start={added + 1}>
        {steps.slice(added).map((step, index) => (
          <li key={keys[added + index]} className="break-words">
            {step}
          </li>
        ))}
      </ol>
      <Button size="sm" isLoading={adding} onClick={() => void add()}>
        {t('workbench.assist.tasks.add_steps')}
      </Button>
    </div>
  );
}

function SentenceIcon({
  lng,
  typed,
  lists,
  onRead,
}: {
  lng: Language;
  typed: string;
  lists: readonly string[];
  onRead: (task: ProposedTask, usage: LLMUsage | null) => void;
}) {
  const { t } = useTranslation(lng);
  const call = useAssistCall<TaskAnswer>();
  const { state } = call;
  useToldFailure(lng, state);
  const words = typed.trim();
  const inTheField = useLatest(words);
  if (!words) return null;
  const read = async () => {
    const answer = await call.run(ASSIST_PATHS.taskFromWords, { sentence: words, lists });
    if (!answer) return;
    // The field moved on while LIA read: its words are the person's, and only the cost stays.
    if (inTheField.current === words) onRead(answer.task, answer.usage);
    else tellCost(answer.usage);
  };
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="h-8 w-8"
      isLoading={state.status === 'running'}
      aria-label={t('workbench.assist.tasks.from_words')}
      title={t('workbench.assist.tasks.from_words')}
      onClick={() => void read()}
    >
      <AssistStars className="h-4 w-4" aria-hidden="true" />
    </Button>
  );
}

/**
 * @param lng - The reader's language.
 * @param lists - The names of the person's lists.
 * @returns LIA inside the quick add; nothing where a click may not ask a model.
 */
export function useQuickAddAssist(
  lng: Language,
  lists: readonly string[]
): QuickAddAssist | undefined {
  const bounds = useAssistBounds();
  if (!bounds) return undefined;
  return {
    icon: (typed, onRead) => (
      <SentenceIcon
        lng={lng}
        typed={typed.slice(0, bounds.instructionMax)}
        lists={lists}
        onRead={onRead}
      />
    ),
    dayLabel: day => datedDay(day, lng),
  };
}

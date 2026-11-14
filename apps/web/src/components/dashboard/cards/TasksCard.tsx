'use client';

import { BellPlus, CalendarClock, Check, ListTodo, Sparkles } from '@/lib/icons';
import { useTranslation } from 'react-i18next';
import { TaskListBadge } from '@/components/workbench/tasks/TaskListBadge';
import { BriefingCard } from '../BriefingCard';
import type { CardItemAction } from './CardItemActions';
import { CardItemRow } from './CardItemRow';
import { homeActs, useHomeAct, useHomeReminder } from './useHomeActs';
import { useHomeTools } from '../HomeTools';
import { chatDraftHref, chatIntentHref } from '@/lib/chat-href';
import { homeLanguage, postponedDay, taskHref } from '@/lib/briefing-tools';
import { useDashboardChat } from '../DashboardNavigation';
import type { Language } from '@/i18n/settings';
import type { CardSection, TaskItem, TasksData } from '@/types/briefing';

interface TasksCardProps {
  section: CardSection<TasksData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  /** Reload after a direct act, independently of manual refresh feedback. */
  onInvalidate?: () => void;
  staggerIndex?: number;
}

/**
 * Tasks card (P15 extension, 2026-07-22).
 *
 * Strictly pending/overdue tasks of EVERY list of the active provider (Google
 * Tasks / Microsoft To Do), each naming its list in a badge (owner, 2026-11-10);
 * a list that could not be read in full is said under the tasks, never passed
 * over. Overdue rows lead with a rose accent. Where the instance
 * offers the « Tools », a task opens in its own list there, and « done » and
 * « tomorrow » are one press each through the Tools' routes, the card read again
 * after (owner, 2026-11-07); a task whose list could not be read, or an instance
 * that keeps the chat, asks LIA instead (ADR-173), prefilled or executed.
 */
export function TasksCard({
  section,
  isRefreshing,
  onRefresh,
  onInvalidate,
  staggerIndex,
}: TasksCardProps) {
  const { i18n } = useTranslation();
  const openChat = useDashboardChat();
  const lng = homeLanguage(i18n.language);
  const { offered, zone } = useHomeTools();
  return (
    <BriefingCard<TasksData>
      titleKey="dashboard.briefing.cards.tasks.title"
      icon={<ListTodo className="h-5 w-5" />}
      tone="teal"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.tasks.empty"
      renderContent={data => (
        <TasksContent
          data={data}
          lng={lng}
          opensTools={offered}
          zone={zone}
          onOpenChat={draft => openChat(chatDraftHref(lng, draft))}
          onExecute={intent => openChat(chatIntentHref(lng, intent))}
          onActed={onInvalidate ?? onRefresh}
        />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

/** « Tomorrow » postpones only what is due by today: a task due later would be brought forward. */
function dueByToday(task: TaskItem): boolean {
  return task.days_until_due !== null && task.days_until_due <= 0;
}

function DueBadge({ task }: { task: TaskItem }) {
  const { t } = useTranslation();
  if (task.days_until_due === null) return null;
  let label: string;
  if (task.overdue) {
    label = t('dashboard.briefing.cards.tasks.overdue_days', {
      count: Math.abs(task.days_until_due),
    });
  } else if (task.days_until_due === 0) {
    label = t('dashboard.briefing.cards.tasks.due_today');
  } else if (task.days_until_due === 1) {
    label = t('dashboard.briefing.cards.tasks.due_tomorrow');
  } else {
    label = t('dashboard.briefing.cards.tasks.due_in_days', { count: task.days_until_due });
  }
  return (
    <span
      className={
        task.overdue
          ? 'shrink-0 text-xs font-semibold text-rose-600 dark:text-rose-300'
          : 'shrink-0 text-xs text-muted-foreground tabular-nums'
      }
    >
      {label}
    </span>
  );
}

function TasksContent({
  data,
  lng,
  opensTools,
  zone,
  onOpenChat,
  onExecute,
  onActed,
}: {
  data: TasksData;
  lng: Language;
  /** The instance offers the Tools: a task opens there, and « done » acts directly. */
  opensTools: boolean;
  /** The account's zone: « tomorrow » is its day. */
  zone: string | undefined;
  onOpenChat: (draft: string) => void;
  onExecute: (intent: string) => void;
  onActed: () => void;
}) {
  const { t } = useTranslation();
  const { busy, run, list } = useHomeAct(onActed);
  const { remind, dialog } = useHomeReminder(lng);

  /**
   * Direct first — the Tools' routes where the task's own list is known, then a reminder — and
   * LIA's acts after: « done » and « tomorrow » are LIA's where the Tools cannot do them.
   */
  const actsOf = (task: TaskItem): CardItemAction[] => {
    const subject = { subject: task.title };
    const { id, list_id: listId } = task;
    const remindAct: CardItemAction = {
      icon: BellPlus,
      label: t('dashboard.briefing.home_acts.remind'),
      onSelect: () => remind(task.title),
    };
    const help = t('dashboard.briefing.intents_exec.task_help', subject);
    const helpAct: CardItemAction = {
      icon: Sparkles,
      label: help,
      opensChat: true,
      onSelect: () => onExecute(help),
    };
    if (opensTools && id && listId) {
      const postponeAct: CardItemAction = {
        icon: CalendarClock,
        label: t('dashboard.briefing.home_acts.postpone'),
        busy: busy === id,
        onSelect: () =>
          void run(
            id,
            () => homeActs.postpone(listId, id, postponedDay(zone, new Date())),
            'dashboard.briefing.home_acts_done.postponed'
          ),
      };
      return [
        {
          icon: Check,
          label: t('dashboard.briefing.home_acts.done'),
          busy: busy === id,
          onSelect: () =>
            void run(
              id,
              () => homeActs.complete(listId, id),
              'dashboard.briefing.home_acts_done.done'
            ),
        },
        ...(dueByToday(task) ? [postponeAct] : []),
        remindAct,
        helpAct,
      ];
    }
    // "Terminé" is an external write — the pipeline's task_update HITL draft
    // still gates the actual provider call (ADR-173).
    const complete = t('dashboard.briefing.intents_exec.task_complete', subject);
    const postpone = t('dashboard.briefing.intents_exec.task_postpone', subject);
    return [
      remindAct,
      { icon: Check, label: complete, opensChat: true, onSelect: () => onExecute(complete) },
      {
        icon: CalendarClock,
        label: postpone,
        opensChat: true,
        onSelect: () => onExecute(postpone),
      },
      helpAct,
    ];
  };

  return (
    <>
      {dialog}
      <ul ref={list} className="space-y-0.5" role="list">
        {data.items.map((task, index) => {
          const intent = t(
            task.overdue
              ? 'dashboard.briefing.intents.task_reschedule'
              : 'dashboard.briefing.intents.task_progress',
            { subject: task.title }
          );
          const href = opensTools ? taskHref(task, lng) : null;
          const target = href
            ? { href, ariaLabel: t('dashboard.briefing.open_in.task', { subject: task.title }) }
            : { onSelect: () => onOpenChat(intent), ariaLabel: intent };
          return (
            <CardItemRow
              key={task.id ?? index}
              {...target}
              tooltip={task.title}
              contentClassName="flex flex-col gap-1.5 leading-snug"
              actions={actsOf(task)}
            >
              {(task.days_until_due !== null || task.list_name) && (
                <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                  {task.days_until_due !== null && (
                    <span className="flex items-center gap-1.5 text-teal-700 dark:text-teal-300">
                      <ListTodo className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                      <DueBadge task={task} />
                    </span>
                  )}
                  {task.list_name && (
                    <TaskListBadge name={task.list_name} label={t('workbench.tasks.list_label')} />
                  )}
                </span>
              )}
              <span
                className={
                  task.overdue
                    ? 'line-clamp-2 break-words text-sm font-semibold text-rose-600 dark:text-rose-300'
                    : 'line-clamp-2 break-words text-sm font-semibold text-foreground/90'
                }
              >
                {task.title}
              </span>
            </CardItemRow>
          );
        })}
      </ul>
      {data.partial && (
        <p role="status" className="pt-2 text-xs text-muted-foreground">
          {t('dashboard.briefing.cards.tasks.partial')}
        </p>
      )}
    </>
  );
}

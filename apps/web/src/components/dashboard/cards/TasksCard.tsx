'use client';

import { CalendarClock, Check, ListTodo } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { CardItemActions } from './CardItemActions';
import { chatDraftHref, chatIntentHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import type { CardSection, TaskItem, TasksData } from '@/types/briefing';

interface TasksCardProps {
  section: CardSection<TasksData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

/**
 * Tasks card (P15 extension, 2026-07-22).
 *
 * Strictly pending/overdue tasks from the active provider (Google Tasks /
 * Microsoft To Do). Overdue rows lead with a rose accent; every row is a
 * button opening the chat prefilled with a direction-aware intent (QW-9
 * `?draft=` pattern — reschedule for overdue, progress for pending).
 */
export function TasksCard({ section, isRefreshing, onRefresh, staggerIndex }: TasksCardProps) {
  const { i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
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
          onOpenChat={draft => openChatDeepLink(chatDraftHref(lng, draft))}
          onExecute={intent => openChatDeepLink(chatIntentHref(lng, intent))}
        />
      )}
      staggerIndex={staggerIndex}
    />
  );
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
  onOpenChat,
  onExecute,
}: {
  data: TasksData;
  onOpenChat: (draft: string) => void;
  onExecute: (intent: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <ul className="space-y-0.5" role="list">
      {data.items.map((task, index) => {
        const intent = t(
          task.overdue
            ? 'dashboard.briefing.intents.task_reschedule'
            : 'dashboard.briefing.intents.task_progress',
          { subject: task.title }
        );
        const completeIntent = t('dashboard.briefing.intents_exec.task_complete', {
          subject: task.title,
        });
        const postponeIntent = t('dashboard.briefing.intents_exec.task_postpone', {
          subject: task.title,
        });
        return (
          // QW-24: action chips as SIBLINGS (nested buttons are invalid HTML).
          // "Terminé" is an external write — the pipeline's task_update HITL
          // draft still gates the actual provider call (ADR-173).
          <li key={index} className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => onOpenChat(intent)}
              aria-label={intent}
              className="min-w-0 flex-1 text-left flex items-baseline justify-between gap-2 text-sm rounded-md px-1.5 py-1 -mx-1.5 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span
                className={
                  task.overdue
                    ? 'truncate font-medium text-rose-600 dark:text-rose-300'
                    : 'truncate font-medium text-foreground/90'
                }
              >
                {task.title}
              </span>
              <DueBadge task={task} />
            </button>
            <CardItemActions
              actions={[
                { icon: Check, label: completeIntent, onSelect: () => onExecute(completeIntent) },
                {
                  icon: CalendarClock,
                  label: postponeIntent,
                  onSelect: () => onExecute(postponeIntent),
                },
              ]}
            />
          </li>
        );
      })}
    </ul>
  );
}

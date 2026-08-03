'use client';

import { useRef, useState } from 'react';
import { Bell, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { BriefingCard } from '../BriefingCard';
import { CardItemActions, type CardItemAction } from './CardItemActions';
import { chatDraftHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import { haptic } from '@/lib/haptics';
import { useApiMutation } from '@/hooks/useApiMutation';
import type { CardSection, ReminderItem, RemindersData } from '@/types/briefing';

interface RemindersCardProps {
  section: CardSection<RemindersData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

/**
 * Reminders on the briefing, now with the one action the card could not
 * perform honestly.
 *
 * Reading is unchanged: the row opens the chat plainly (the reminder fires on
 * its own; no prefilled intent is needed).
 *
 * **Cancelling names the reminder by its id.** The agent path resolves its
 * target through the model, from a content substring — two reminders worded
 * alike and the wrong one goes. The HITL draft that guarded it is replaced,
 * not removed: the confirmation moves to an `AlertDialog` on the card, exactly
 * like deleting a routine. A deletion still asks before it acts; it simply
 * asks where the reader already is.
 *
 * Rows without an id (payloads cached before the field existed) keep their
 * reading affordance and offer no cancel: an action we cannot target exactly
 * is the ambiguity this replaces.
 */
export function RemindersCard({
  section,
  isRefreshing,
  onRefresh,
  staggerIndex,
}: RemindersCardProps) {
  const { i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  return (
    <BriefingCard<RemindersData>
      titleKey="dashboard.briefing.cards.reminders.title"
      icon={<Bell className="h-5 w-5" />}
      tone="amber"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.reminders.empty"
      renderContent={data => (
        <RemindersContent
          data={data}
          onOpenChat={() => openChatDeepLink(chatDraftHref(lng))}
          onCancelled={onRefresh}
        />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

function RemindersContent({
  data,
  onOpenChat,
  onCancelled,
}: {
  data: RemindersData;
  onOpenChat: () => void;
  /** Reload from the server rather than guessing the new list. */
  onCancelled: () => void;
}) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<ReminderItem | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const { mutate } = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'RemindersCard',
  });

  const confirmCancel = async () => {
    if (!pending?.id) return;
    const target = pending;
    setPending(null);
    try {
      await mutate(`/reminders/${target.id}`);
      haptic('confirm');
      toast.success(t('dashboard.briefing.actions.cancel_reminder_done'));
      // Take focus BEFORE asking for the refetch, while the row the dialog
      // was opened from still exists: Radix restores focus to that trigger,
      // and a moment later the refetch removes it, dropping the keyboard user
      // on <body>. The card's own named region is the anchor — it outlives
      // every row, including the last one.
      listRef.current?.closest<HTMLElement>('[role="region"]')?.focus();
      onCancelled();
    } catch {
      // Never a silent failure: the reminder will still fire, and the reader
      // must know their cancellation did not take.
      toast.error(t('common.error'));
    }
  };

  return (
    <>
      <ul ref={listRef} className="space-y-1.5" role="list">
        {data.items.map((reminder, index) => {
          const actions: CardItemAction[] = reminder.id
            ? [
                {
                  icon: X,
                  label: t('dashboard.briefing.actions.cancel_reminder'),
                  onSelect: () => setPending(reminder),
                },
              ]
            : [];
          return (
            <li key={reminder.id ?? index} className="flex items-start gap-1">
              {/* QW-9: reminders open the chat plainly (product decision — the
                  reminder will fire on its own; no prefilled intent needed).
                  The action chips are SIBLINGS of this button, never inside
                  it: nested buttons are invalid HTML and unreachable by AT. */}
              <button
                type="button"
                onClick={onOpenChat}
                aria-label={t('dashboard.briefing.intents.reminder_aria')}
                className="min-w-0 flex-1 text-left flex flex-col gap-0.5 leading-tight rounded-md px-1.5 py-1 -mx-1.5 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="text-xs font-semibold text-amber-700 dark:text-amber-300 tabular-nums">
                  {reminder.trigger_at_local}
                </span>
                <span className="text-sm text-foreground/90 line-clamp-2 leading-snug">
                  {reminder.content}
                </span>
              </button>
              {actions.length > 0 && <CardItemActions actions={actions} />}
            </li>
          );
        })}
      </ul>

      <AlertDialog open={pending !== null} onOpenChange={open => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('dashboard.briefing.actions.cancel_reminder_title')}
            </AlertDialogTitle>
            {/* The reminder's own words: confirming a deletion without naming
                what disappears asks the reader to trust their memory. */}
            <AlertDialogDescription>
              {t('dashboard.briefing.actions.cancel_reminder_description', {
                content: pending?.content ?? '',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void confirmCancel()}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('common.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

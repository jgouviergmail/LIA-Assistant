'use client';
/**
 * What a reminder that rang lets you do, right under its bubble.
 *
 * ADR-268 amendment 2026-11-16. The `PeerMessageActions` precedent: a
 * self-gated, metadata-driven block that renders NOTHING unless the bubble is a
 * reminder whose occurrence was recorded and can still be postponed. It then
 * reads the occurrence's state (another device may have postponed it already)
 * and offers the three « later » — in the delays the deployment configured —
 * and « stop this reminder » when it repeats, behind a confirmation.
 *
 * A press is the person's own act: no model, no turn, no confirmation card. Its
 * verdict replaces the buttons, is announced and takes the focus; a press the
 * series already covers keeps them, since a shorter delay still works.
 *
 * `ReminderFiringButtons` is the same row for a surface that knows only the
 * occurrence (the world's device).
 */
import type { TFunction } from 'i18next';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { useConfirm } from '@/components/ui/use-confirm';
import { useAuth } from '@/hooks/useAuth';
import { useReminderFiring, type UseReminderFiringResult } from '@/hooks/useReminderFiring';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { formatInstant } from '@/lib/format-instant';
import { AlarmClock, BellOff, Sunrise } from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  delayLabelKey,
  reminderFiringOf,
  type FiringVerdict,
  type ReminderFiringState,
  type SnoozeChoice,
} from '@/lib/reminder-firing';

// The height of the bubble's icon chips (`ActionChipButton`: 14 px glyph, 6 px
// padding, 1 px border = 28 px): the delays sit in the same row, centred on it.
const CHIP =
  'inline-flex h-7 items-center gap-1.5 rounded-md border border-border/30 bg-background/80 ' +
  'px-2 text-xs font-medium text-foreground/90 transition-colors hover:bg-background ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ' +
  'aria-disabled:cursor-not-allowed aria-disabled:opacity-50';

/** A timer's longest delay: past it, `setTimeout` fires at once. */
const MAX_TIMER_MS = 2_147_483_647;

export interface ReminderFiringActionsProps {
  metadata: Record<string, unknown> | undefined;
}

export function ReminderFiringActions({ metadata }: ReminderFiringActionsProps) {
  // Read when the bubble mounts, like an image's expiry: a window already
  // closed offers nothing and asks the server nothing.
  const [mountedAt] = useState(() => Date.now());
  const firingId = reminderFiringOf(metadata, mountedAt);
  if (!firingId) return null;
  return <ReminderFiringButtons firingId={firingId} trailing />;
}

/** What the row shows, from the server's state and what this page learned. */
interface FiringView {
  snoozedUntil: string | null;
  closed: boolean;
  stopped: boolean;
  stoppable: boolean;
  offersDelays: boolean;
}

function firingView(
  state: ReminderFiringState,
  verdict: FiringVerdict | undefined,
  windowClosed: boolean
): FiringView {
  const snoozedUntil = verdict?.snoozedUntil ?? state.snoozed_until;
  const closed = verdict?.expired === true || windowClosed;
  const stopped = verdict?.stopped === true;
  return {
    snoozedUntil,
    closed,
    stopped,
    stoppable: state.stoppable && !stopped,
    offersDelays: !snoozedUntil && !closed,
  };
}

/** Two facts, said together: a copy postponed before a stop still rings. */
function statusOf(
  view: FiringView,
  notice: string | null,
  t: TFunction,
  at: (iso: string) => string
): string {
  const occurrence = view.snoozedUntil
    ? t('reminders.firing.snoozed', { when: at(view.snoozedUntil) })
    : view.closed
      ? t('reminders.firing.expired')
      : notice;
  return [occurrence, view.stopped ? t('reminders.firing.stopped') : null]
    .filter(Boolean)
    .join(' ');
}

/** The three « later », labelled in the delays the server configured. */
function delaysOf(state: ReminderFiringState, t: TFunction) {
  const delay = (minutes: number) => {
    const { key, count } = delayLabelKey(minutes);
    return t(key, { count });
  };
  return [
    { choice: 'short' as const, label: delay(state.short_minutes) },
    { choice: 'long' as const, label: delay(state.long_minutes) },
    { choice: 'morning' as const, label: t('reminders.firing.tomorrow_morning') },
  ];
}

/**
 * Whether the window closed: at the read, or since — the page may stay open
 * past it, and the delays then go without a press being refused first.
 */
function useWindowClosed(snoozableUntil: string | undefined): boolean {
  const [readAt] = useState(() => Date.now());
  const [elapsed, setElapsed] = useState(false);
  const closesAt = snoozableUntil ? Date.parse(snoozableUntil) : Number.NaN;
  useEffect(() => {
    if (!Number.isFinite(closesAt) || closesAt <= readAt) return;
    const timer = window.setTimeout(
      () => setElapsed(true),
      Math.min(closesAt - readAt, MAX_TIMER_MS)
    );
    return () => window.clearTimeout(timer);
  }, [closesAt, readAt]);
  return elapsed || (Number.isFinite(closesAt) && closesAt <= readAt);
}

/**
 * The two presses: a delay, and « stop » behind a confirmation. A settled press
 * moves the focus to the verdict (by an effect, where a ref may be read): the
 * pressed button goes with it, and the focus must not fall back to the page.
 */
function useFiringPresses(firing: UseReminderFiringResult, at: (iso: string) => string) {
  const { t } = useTranslation();
  const { confirm, confirmDialog } = useConfirm();
  const [notice, setNotice] = useState<string | null>(null);
  const statusRef = useRef<HTMLParagraphElement>(null);
  const [settled, setSettled] = useState(0);
  useEffect(() => {
    if (settled > 0) statusRef.current?.focus();
  }, [settled]);
  const { busy, snooze, stop } = firing;

  const press = async (choice: SnoozeChoice) => {
    if (busy) return;
    setNotice(null);
    try {
      const answer = await snooze(choice);
      if (answer?.outcome === 'collides' && answer.next_occurrence_at) {
        setNotice(t('reminders.firing.collides', { when: at(answer.next_occurrence_at) }));
      } else if (answer) {
        setSettled(count => count + 1);
      }
    } catch {
      toast.error(t('reminders.firing.failed'));
    }
  };

  const pressStop = async () => {
    if (busy) return;
    const accepted = await confirm({
      title: t('reminders.firing.stop_title'),
      description: t('reminders.firing.stop_description'),
      confirmLabel: t('reminders.firing.stop'),
    });
    if (!accepted) return;
    try {
      if (await stop()) setSettled(count => count + 1);
    } catch {
      toast.error(t('reminders.firing.stop_failed'));
    }
  };

  return { notice, statusRef, confirmDialog, press, pressStop };
}

export interface ReminderFiringButtonsProps {
  firingId: string;
  /**
   * The row's last items from `lg` up: in the bubble's action row the delays
   * and their verdict sit at its right end on a desktop, after the bubble's own
   * icons. A column (the world's device) leaves them where they start.
   */
  trailing?: boolean;
}

export function ReminderFiringButtons({ firingId, trailing = false }: ReminderFiringButtonsProps) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const firing = useReminderFiring(firingId);
  const windowClosed = useWindowClosed(firing.state?.snoozable_until);
  const at = (iso: string) =>
    formatInstant(
      iso,
      getIntlLocale(i18n.language as Language),
      'short',
      user?.timezone ?? undefined
    );
  const { notice, statusRef, confirmDialog, press, pressStop } = useFiringPresses(firing, at);

  if (firing.unavailable || !firing.state) return null;
  const view = firingView(firing.state, firing.verdict, windowClosed);
  const status = statusOf(view, notice, t, at);

  // Inside the bubble's action row, the delays AND the verdict are items of
  // that row: no margin of their own, centred with its icons, at its right end
  // on a desktop. Silent, the live region stays mounted but out of the flow.
  return (
    <div
      role="group"
      aria-label={t('reminders.firing.actions_label')}
      className={cn('flex flex-wrap items-center gap-1', trailing && 'lg:ml-auto lg:justify-end')}
    >
      {confirmDialog}
      <FiringButtonsRow
        view={view}
        delays={delaysOf(firing.state, t)}
        busy={firing.busy}
        onPress={press}
        onStop={pressStop}
      />
      {/* Mounted before it speaks: a live region added with its words is not read. */}
      <p
        ref={statusRef}
        role="status"
        aria-live="polite"
        tabIndex={-1}
        className={status ? 'px-1 text-xs text-muted-foreground focus:outline-none' : 'sr-only'}
      >
        {status}
      </p>
    </div>
  );
}

function FiringButtonsRow({
  view,
  delays,
  busy,
  onPress,
  onStop,
}: {
  view: FiringView;
  delays: { choice: SnoozeChoice; label: string }[];
  busy: boolean;
  onPress: (choice: SnoozeChoice) => Promise<void>;
  onStop: () => Promise<void>;
}) {
  const { t } = useTranslation();
  return (
    <>
      {view.offersDelays &&
        delays.map(({ choice, label }) => (
          <button
            key={choice}
            type="button"
            className={CHIP}
            aria-disabled={busy || undefined}
            onClick={() => void onPress(choice)}
          >
            {choice === 'morning' ? (
              <Sunrise className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
            ) : (
              <AlarmClock className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
            )}
            {label}
          </button>
        ))}
      {view.stoppable && (
        <button
          type="button"
          className={CHIP}
          aria-disabled={busy || undefined}
          onClick={() => void onStop()}
        >
          <BellOff className="h-3.5 w-3.5 text-destructive" aria-hidden="true" />
          {t('reminders.firing.stop')}
        </button>
      )}
    </>
  );
}

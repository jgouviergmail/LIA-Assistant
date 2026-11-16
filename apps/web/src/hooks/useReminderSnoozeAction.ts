/**
 * The toast's « later » for a reminder that just rang (ADR-268 amendment 2026-11-16).
 *
 * A reminder arriving on the open page shows a toast; when its occurrence was
 * recorded, the toast offers the SHORT delay — the one a person reaches for
 * while doing something else — and the bubble in the thread keeps the full set.
 * The press's verdict is said in a toast of its own and remembered page-wide,
 * so the bubble of the same occurrence follows it.
 *
 * The builder's identity never changes: the notification stream reopens when a
 * handler it holds changes identity, and an event published meanwhile is lost
 * (measured 2026-11-15). What it reads is kept in a ref, read at the click.
 */

import type { TFunction } from 'i18next';
import { useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { useSnoozeFiring } from '@/hooks/useReminderFiring';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { formatInstant } from '@/lib/format-instant';
import { delayLabelKey, type ReminderSnoozeOffer, type SnoozeVerdict } from '@/lib/reminder-firing';

/** A toast's action button. */
export interface ToastAction {
  label: string;
  onClick: () => void;
}

/**
 * Build the toast's « in N min » action for an offer.
 *
 * @param timeZone - The account's display zone, for the verdict's instant.
 * @returns A stable builder: an offer in, its action out (none without an offer).
 */
export function useReminderSnoozeAction(
  timeZone: string | undefined
): (offer: ReminderSnoozeOffer | undefined) => ToastAction | undefined {
  const { t, i18n } = useTranslation();
  const { snooze } = useSnoozeFiring('chat');
  const live = useRef({ t, language: i18n.language, timeZone, snooze });
  useEffect(() => {
    live.current = { t, language: i18n.language, timeZone, snooze };
  });

  return useCallback((offer: ReminderSnoozeOffer | undefined) => {
    if (!offer) return undefined;
    const { key, count } = delayLabelKey(offer.shortMinutes);
    return {
      label: live.current.t(key, { count }),
      onClick: () => {
        void (async () => {
          const { t: translate, language, timeZone: zone, snooze: press } = live.current;
          try {
            say(await press(offer.firingId, 'short'), translate, language, zone);
          } catch {
            toast.error(translate('reminders.firing.failed'));
          }
        })();
      },
    };
  }, []);
}

function say(
  verdict: SnoozeVerdict | undefined,
  t: TFunction,
  language: string,
  timeZone: string | undefined
): void {
  if (!verdict) return;
  const at = (iso: string) =>
    formatInstant(iso, getIntlLocale(language as Language), 'short', timeZone);
  if (verdict.snoozed_until) {
    toast.success(t('reminders.firing.snoozed', { when: at(verdict.snoozed_until) }));
  } else if (verdict.outcome === 'expired') {
    toast.info(t('reminders.firing.expired'));
  } else if (verdict.outcome === 'collides' && verdict.next_occurrence_at) {
    toast.info(t('reminders.firing.collides', { when: at(verdict.next_occurrence_at) }));
  }
}

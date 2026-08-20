'use client';

/**
 * OpenOffersList — the proposals inbox rows (Lot 5-C2).
 *
 * Each row is an UNDECIDED missed-routine offer (ADR-214): LIA noticed a
 * learned routine did not happen and offered to help. Accepting opens the
 * chat prefilled with the offer (nothing auto-sends — HITL intact) and
 * records a 👍; declining records a 👎. Both feed the habit's Bayesian
 * signals through the EXISTING feedback endpoint — the inbox adds a
 * surface, never a second authority.
 */

import { Check, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { RowActions } from '@/components/ui/row-actions';
import apiClient from '@/lib/api-client';
import { chatDraftHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import type { HeartbeatNotification } from '@/hooks/useHeartbeatHistory';

export interface OpenOffersListProps {
  offers: HeartbeatNotification[];
  /** Current URL locale segment (deep-link building). */
  lng: string;
  /** Intl locale for timestamps. */
  locale: string;
  /** Reload the section after a decision (the row leaves the OPEN set). */
  onDecided: () => void;
}

async function submitDecision(id: string, feedback: 'thumbs_up' | 'thumbs_down'): Promise<void> {
  await apiClient.patch(`/heartbeat/notifications/${id}/feedback`, { feedback });
}

export function OpenOffersList({ offers, lng, locale, onDecided }: OpenOffersListProps) {
  const { t } = useTranslation();
  const timeFormat = new Intl.DateTimeFormat(locale, {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });

  const decide = async (offer: HeartbeatNotification, accept: boolean) => {
    try {
      await submitDecision(offer.id, accept ? 'thumbs_up' : 'thumbs_down');
    } catch {
      // Never silent: the row stays either way, and saying nothing would
      // read as "it worked" — the worse of the two readings.
      toast.error(t('common.error'));
      return;
    }
    if (accept) {
      // The offer text becomes the chat draft — an explicit user send,
      // never an auto-send (the ledger's one-tap doctrine).
      openChatDeepLink(chatDraftHref(lng, offer.content));
    }
    onDecided();
  };

  return (
    <ul className="space-y-2" role="list">
      {offers.map(offer => (
        <li
          key={offer.id}
          className="flex items-start gap-3 rounded-xl border bg-card px-4 py-3"
        >
          <div className="min-w-0 flex-1">
            <p className="text-sm text-foreground/90">{offer.content}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {timeFormat.format(new Date(offer.created_at))}
            </p>
          </div>
          <RowActions
            menuLabel={t('notifications_hub.sections.offers.menu')}
            actions={[
              {
                key: 'accept',
                icon: Check,
                label: t('notifications_hub.sections.offers.accept'),
                onSelect: () => void decide(offer, true),
              },
              {
                key: 'dismiss',
                icon: X,
                label: t('notifications_hub.sections.offers.dismiss'),
                onSelect: () => void decide(offer, false),
              },
            ]}
          />
        </li>
      ))}
    </ul>
  );
}

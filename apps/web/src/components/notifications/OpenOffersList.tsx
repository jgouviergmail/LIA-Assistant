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

import { useRef, useState } from 'react';
import { Check, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { formatInstant } from '@/lib/format-instant';
import apiClient from '@/lib/api-client';
import { chatDraftHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import type { HeartbeatNotification } from '@/hooks/useHeartbeatHistory';

export interface OpenOffersListProps {
  offers: HeartbeatNotification[];
  /** Intl locale for timestamps. */
  locale: string;
  decisions: ReturnType<typeof useOfferDecisions>;
}

async function submitDecision(id: string, feedback: 'thumbs_up' | 'thumbs_down'): Promise<void> {
  await apiClient.patch(`/heartbeat/notifications/${id}/feedback`, { feedback });
}

/** Lives above the fold so pending and completed decisions survive its unmount. */
export function useOfferDecisions({
  lng,
  onDecided,
}: {
  lng: string;
  onDecided: (restoreFocus: boolean) => void;
}) {
  const { t } = useTranslation();
  const lock = useRef(false);
  const [pending, setPending] = useState<{ id: string; accept: boolean } | null>(null);
  const [decided, setDecided] = useState<ReadonlySet<string>>(() => new Set());

  const decide = async (offer: HeartbeatNotification, accept: boolean) => {
    if (lock.current || decided.has(offer.id)) return;
    const initiator = document.activeElement;
    lock.current = true;
    setPending({ id: offer.id, accept });
    try {
      await submitDecision(offer.id, accept ? 'thumbs_up' : 'thumbs_down');
      setDecided(previous => new Set(previous).add(offer.id));
    } catch {
      // Never silent: the row stays either way, and saying nothing would
      // read as "it worked" — the worse of the two readings.
      toast.error(t('common.error'));
      return;
    } finally {
      lock.current = false;
      setPending(null);
    }
    if (accept) {
      // The offer text becomes the chat draft — an explicit user send,
      // never an auto-send (the ledger's one-tap doctrine).
      openChatDeepLink(chatDraftHref(lng, offer.content));
    }
    onDecided(!accept && document.activeElement === initiator);
  };

  return { pending, decided, decide };
}

function OfferDecisionButton({
  offer,
  accept,
  decisions,
}: {
  offer: HeartbeatNotification;
  accept: boolean;
  decisions: ReturnType<typeof useOfferDecisions>;
}) {
  const { t } = useTranslation();
  const { pending, decided, decide } = decisions;
  const busy = pending?.id === offer.id && pending.accept === accept;
  const Icon = accept ? Check : X;
  return (
    <Button
      size="sm"
      variant={accept ? 'default' : 'outline'}
      className="h-auto min-h-11 whitespace-normal py-2"
      aria-disabled={Boolean(pending) || decided.has(offer.id) || undefined}
      aria-busy={busy || undefined}
      onClick={() => void decide(offer, accept)}
    >
      {busy ? (
        <LoadingSpinner className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Icon className="h-4 w-4" aria-hidden="true" />
      )}
      {t(`notifications_hub.sections.offers.${accept ? 'accept' : 'dismiss'}`)}
    </Button>
  );
}

export function OpenOffersList({ offers, locale, decisions }: OpenOffersListProps) {
  return (
    <ul className="space-y-2" role="list">
      {offers.map(offer => (
        <li
          key={offer.id}
          className="min-w-0 space-y-3 border-t border-border/50 py-4 first:border-t-0 first:pt-0"
        >
          <div className="min-w-0 flex-1">
            <p className="break-words whitespace-pre-line text-sm leading-relaxed text-foreground/90">
              {offer.content}
            </p>
            <p className="mt-0.5 text-xs font-bold text-muted-foreground">
              {formatInstant(offer.created_at, locale)}
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
            <OfferDecisionButton offer={offer} accept decisions={decisions} />
            <OfferDecisionButton offer={offer} accept={false} decisions={decisions} />
          </div>
        </li>
      ))}
    </ul>
  );
}

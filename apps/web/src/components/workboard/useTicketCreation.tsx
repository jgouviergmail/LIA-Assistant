'use client';
/**
 * One creation form, whether opened by hand, from the « + » of a lane, or
 * from an account-owned AI proposal.
 *
 * `start` opens it in no lane and `startIn` in the lane it was asked from: two
 * verbs rather than one optional argument, because `start` is handed straight
 * to click handlers and a click event is not a category.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import { useHandoff } from '@/hooks/useHandoff';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import type { UseWorkboardResult } from '@/hooks/useWorkboard';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PeerName } from '@/lib/workboard/display';
import { toastWorkboardError } from '@/lib/workboard/errors';
import type { CategoryOption, TicketCreateBody } from '@/types/workboard';
import { TicketForm } from './TicketForm';

export function useTicketCreation({
  lng,
  peers,
  board,
  embedded,
  blocked,
  categories,
}: {
  lng: Language;
  peers: readonly PeerName[];
  board: UseWorkboardResult;
  embedded: boolean;
  blocked: boolean;
  /** The reader's own categories; the form asks for one only when there are some. */
  categories: readonly CategoryOption[];
}) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const [open, setOpen] = useState(false);
  const [proposal, setProposal] = useState<Pick<TicketCreateBody, 'title' | 'description'>>();
  // The lane the form was opened from; null for none.
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const ready = !embedded && !board.firstLoad && !board.isUnavailable && !board.error;
  useHandoff(
    'ticket',
    ready,
    handed => {
      setProposal(handed.ticket);
      setCategoryId(null);
      setOpen(true);
    },
    open || blocked
  );
  const startIn = (lane: string | null) => {
    setProposal(undefined);
    setCategoryId(lane);
    setOpen(true);
  };
  return {
    start: () => startIn(null),
    startIn,
    form: open && (
      <TicketForm
        open
        lng={lng}
        peers={peers}
        initialDraft={proposal}
        categories={categories}
        initialCategoryId={categoryId}
        onClose={() => setOpen(false)}
        onCreate={async body => {
          const result = await board.create(body);
          if (!isCurrent()) return { ok: false };
          if (result.ok) {
            toast.success(t('workboard.created'));
            setOpen(false);
          } else toastWorkboardError(t, result.errorCode);
          return result;
        }}
      />
    ),
  };
}

'use client';
/** One creation form, whether opened by hand or from an account-owned AI proposal. */
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
import type { TicketCreateBody } from '@/types/workboard';
import { TicketForm } from './TicketForm';

export function useTicketCreation({
  lng,
  peers,
  board,
  embedded,
  blocked,
}: {
  lng: Language;
  peers: readonly PeerName[];
  board: UseWorkboardResult;
  embedded: boolean;
  blocked: boolean;
}) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const [open, setOpen] = useState(false);
  const [proposal, setProposal] = useState<Pick<TicketCreateBody, 'title' | 'description'>>();
  const ready = !embedded && !board.firstLoad && !board.isUnavailable && !board.error;
  useHandoff(
    'ticket',
    ready,
    handed => {
      setProposal(handed.ticket);
      setOpen(true);
    },
    open || blocked
  );
  return {
    start: () => {
      setProposal(undefined);
      setOpen(true);
    },
    form: open && (
      <TicketForm
        open
        lng={lng}
        peers={peers}
        initialDraft={proposal}
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

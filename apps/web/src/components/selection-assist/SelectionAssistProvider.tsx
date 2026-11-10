'use client';
/** Account and navigation own the transient selection; children keep their existing React lifetime. */
import { useMemo, type ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { useAppConfig } from '@/hooks/useAppConfig';
import { canRecordVoice } from '@/hooks/useVoiceInput';
import { capabilityEnabled } from '@/lib/capability-state';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useSelectionAssistTarget } from '@/hooks/useSelectionAssistTarget';
import { useHandoffNavigation, useHandoffOwner } from '@/hooks/useHandoff';
import type { Language } from '@/i18n/settings';
import {
  selectionOfferSchema,
  type CreationProposal,
  type SelectionOffer,
} from '@/lib/selection-assist/contracts';
import { createSelectionStore } from '@/lib/selection-assist/store';
import { SelectionContext } from './context';
import { SelectionHost } from './SelectionHost';

export function SelectionAssistProvider({
  lng,
  children,
  onProposal,
}: {
  lng: Language;
  children: ReactNode;
  onProposal?: (proposal: CreationProposal) => void;
}) {
  const { user } = useAuth();
  const pathname = usePathname();
  const owner = user?.is_active ? user.id : null;
  const { config, error: configError } = useAppConfig(!!owner);
  const dictates =
    !!owner &&
    !configError &&
    capabilityEnabled(config?.capabilities, 'stt', undefined) &&
    canRecordVoice();
  useHandoffOwner(owner);
  const navigate = useHandoffNavigation(lng);
  const receiveProposal = useMemo(
    () =>
      onProposal ??
      ((proposal: CreationProposal) => {
        if (proposal.kind === 'task') navigate({ kind: 'task', ...proposal.task });
        else if (proposal.kind === 'event')
          navigate({
            kind: 'event',
            summary: proposal.event.summary,
            description: proposal.event.description,
            proposal: proposal.event,
          });
        else navigate(proposal);
      }),
    [onProposal, navigate]
  );
  const store = useMemo(() => ({ ...createSelectionStore(), owner, pathname }), [owner, pathname]);
  const { data, error } = useApplicationAccountQuery<SelectionOffer>(
    '/tool-assists/selection',
    'SelectionAssist',
    !!owner
  );
  const parsed = useMemo(() => selectionOfferSchema.safeParse(data), [data]);
  const offer = owner && !error && parsed.success ? parsed.data : null;
  useSelectionAssistTarget(store, !!offer || dictates, dictates);
  const value = useMemo(
    () => ({ lng, store, offer, dictates, onProposal: receiveProposal }),
    [lng, store, offer, dictates, receiveProposal]
  );
  return (
    <SelectionContext.Provider value={value}>
      {children}
      <SelectionHost id={null} />
    </SelectionContext.Provider>
  );
}

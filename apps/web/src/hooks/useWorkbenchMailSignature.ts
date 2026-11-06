'use client';

/**
 * What the active mailbox signs with (ADR-369, lot 7, A3): read once for the mail screen,
 * from LIA's own records, and written from its settings. `settled` says the answer is in,
 * whatever it was: a signature that could not be read is no reason to keep a message waiting.
 */
import { useCallback } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import type { MailSignature } from '@/lib/workbench/types';

const SIGNATURE_PATH = '/workbench/mail/signature';

export interface WorkbenchMailSignature {
  text: string;
  /** What a message's body gains to carry it. */
  block: string;
  settled: boolean;
  save: (text: string) => Promise<void>;
}

export function useWorkbenchMailSignature(): WorkbenchMailSignature {
  const { item, loading, refresh } = useWorkbenchItem<MailSignature>(SIGNATURE_PATH, {});
  const { mutate: put } = useApiMutation<{ text: string }, MailSignature>({
    method: 'PUT',
    componentName: 'WorkbenchMailSignature',
    retainResponse: false,
  });

  const save = useCallback(
    async (text: string) => {
      await put(SIGNATURE_PATH, { text });
      await refresh();
    },
    [put, refresh]
  );

  return { text: item?.text ?? '', block: item?.block ?? '', settled: !loading, save };
}

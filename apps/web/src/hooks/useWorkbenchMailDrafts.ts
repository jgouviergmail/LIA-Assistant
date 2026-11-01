'use client';

/**
 * The drafts of the mail screen (ADR-369, Task 4.7), where the provider keeps
 * drafts (the descriptor's `drafts`): one cursor listing, newest first, and
 * the trash — never all-or-nothing, each draft answered (`WorkbenchActOutcome`).
 * A draft opened in the composer is read whole by its own read (its revision
 * travels with it); a saved or sent one re-reads the listing in place.
 */
import { useCallback } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import apiClient from '@/lib/api-client';
import { useWorkbenchPage, type WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import type { WorkbenchActOutcome, MailDraft, MailDraftSummary } from '@/lib/workbench/types';

const NO_PARAMS = {};

export interface WorkbenchMailDrafts {
  drafts: WorkbenchPageState<MailDraftSummary>;
  trash: (ids: readonly string[]) => Promise<WorkbenchActOutcome>;
  /** One draft, whole, with the revision the composer edits and sends against. */
  read: (id: string) => Promise<MailDraft>;
}

/** @param enabled - Whether the drafts are on screen (nothing is read otherwise). */
export function useWorkbenchMailDrafts(enabled: boolean): WorkbenchMailDrafts {
  const drafts = useWorkbenchPage<MailDraftSummary>(
    enabled ? '/workbench/mail/drafts' : null,
    NO_PARAMS
  );
  const { replaceItem } = drafts;
  const { mutate: post } = useApiMutation<{ draft_ids: string[] }, WorkbenchActOutcome>({
    method: 'POST',
    componentName: 'WorkbenchMailDrafts',
  });

  const trash = useCallback(
    async (ids: readonly string[]) => {
      const outcome = (await post('/workbench/mail/drafts/trash', { draft_ids: [...ids] })) ?? {
        done: [],
        failed: [],
      };
      for (const id of outcome.done) replaceItem(id, null);
      return outcome;
    },
    [post, replaceItem]
  );

  const read = useCallback(
    (id: string) => apiClient.get<MailDraft>('/workbench/mail/draft', { params: { id } }),
    []
  );

  return { drafts, trash, read };
}

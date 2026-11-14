'use client';

import { useApiQuery } from '@/hooks/useApiQuery';
import { getApiErrorStatus } from '@/lib/api-error';
import type { ConversationSummary } from '@/types/conversation';

interface TargetRequest {
  id: string | null;
  revision: number | null;
  malformed: boolean;
}

function ownedRecord(
  row: ConversationSummary | null | undefined,
  ownerId: string,
  id: string | null
) {
  if (!row || row.user_id !== ownerId) return null;
  const matches = id === null ? row.kind === 'main' : row.id === id;
  return matches ? row : null;
}

/** An explicit URL is never resolved through Main's compatibility endpoint. */
export function useSelectedDiscussion(
  ownerId: string,
  location: TargetRequest,
  catalogueAvailable: boolean,
  onVerified: (result: ConversationSummary | null) => void
) {
  const { id, revision, malformed } = location;
  const enabled = !malformed && (catalogueAvailable || id !== null);
  const query = useApiQuery<ConversationSummary | null>(
    id === null ? '/conversations/me' : `/conversations/${encodeURIComponent(id)}`,
    {
      componentName: 'SelectedDiscussion',
      enabled,
      onSuccess: row => onVerified(ownedRecord(row, ownerId, id)),
    }
  );
  const result = query.data;
  const selected = ownedRecord(result, ownerId, id);
  const virtualMain = id === null && (!catalogueAvailable || result === null);
  const invalidRecord = result !== undefined && selected === null && !virtualMain;
  const staleRevision = selected !== null && revision !== null && selected.revision !== revision;
  const refused =
    malformed || invalidRecord || staleRevision || getApiErrorStatus(query.error) === 404;
  return {
    selected,
    ready: !refused && (selected !== null || virtualMain),
    refused,
    error: Boolean(query.error),
    refetch: query.refetch,
    acceptData: query.acceptData,
  };
}

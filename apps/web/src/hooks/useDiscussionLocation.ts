'use client';

import { useCallback, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { replaceChatDiscussion } from '@/lib/chat-location';

const DISCUSSION_ID = /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i;

function parseRevision(raw: string | null): number | null {
  if (raw === null) return null;
  return /^\d+$/.test(raw) && Number.isSafeInteger(Number(raw)) ? Number(raw) : NaN;
}

export function useDiscussionLocation(embedded: boolean | undefined) {
  const searchParams = useSearchParams();
  const [localId, setLocalId] = useState<string | null>(null);
  const id = embedded ? localId : (searchParams?.get('conversation')?.toLowerCase() ?? null);
  const revision = embedded
    ? null
    : parseRevision(searchParams?.get('conversation_revision') ?? null);
  const malformed =
    (id !== null && !DISCUSSION_ID.test(id)) ||
    Number.isNaN(revision) ||
    (id === null && revision !== null);
  const choose = useCallback(
    (nextId: string | null) => {
      if (embedded) setLocalId(nextId);
      else replaceChatDiscussion(nextId);
    },
    [embedded]
  );
  return { id, revision, malformed, choose };
}

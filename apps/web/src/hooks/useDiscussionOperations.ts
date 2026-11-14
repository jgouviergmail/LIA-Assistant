'use client';

import { useCallback } from 'react';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useScopedRequest } from '@/hooks/useScopedRequest';
import apiClient from '@/lib/api-client';
import { getApiErrorStatus } from '@/lib/api-error';
import type {
  ConversationCreateRequest,
  ConversationCreateResult,
  ConversationOperation,
  ConversationOperationRequest,
  ConversationOperationResult,
  ConversationSummary,
  ConversationRenameRequest,
} from '@/types/conversation';

function matchesOperation(
  result: ConversationOperationResult | undefined,
  target: ConversationSummary,
  action: ConversationOperation,
  operationId: string
): result is ConversationOperationResult {
  if (!result?.logical_applied || result.operation_id !== operationId) return false;
  if (result.conversation_id !== target.id || result.old_revision !== target.revision) return false;
  return result.new_revision === (action === 'reset' ? target.revision + 1 : null);
}

/** No operation can survive a change of authenticated browser owner. */
export function useDiscussionOperations(ownerId: string) {
  const owned = useScopedRequest(ownerId);
  const { mutate: postCreate } = useApiMutation<
    ConversationCreateRequest,
    ConversationCreateResult
  >({
    method: 'POST',
    componentName: 'DiscussionCreate',
    retainResponse: false,
  });
  const { mutate: postReset } = useApiMutation<
    ConversationOperationRequest,
    ConversationOperationResult
  >({
    method: 'POST',
    componentName: 'DiscussionReset',
    retainResponse: false,
  });
  const { mutate: patchTitle } = useApiMutation<ConversationRenameRequest, ConversationSummary>({
    method: 'PATCH',
    componentName: 'DiscussionRename',
    retainResponse: false,
  });
  const { mutate: deleteRow } = useApiMutation<
    ConversationOperationRequest,
    ConversationOperationResult
  >({
    method: 'DELETE',
    componentName: 'DiscussionDelete',
    retainResponse: false,
  });
  const create = useCallback(
    async (request: ConversationCreateRequest) => {
      const result = await owned(signal => postCreate('/conversations', request, { signal }));
      if (result?.conversation.kind !== 'secondary' || result.conversation.user_id !== ownerId) {
        throw new Error('Discussion creation did not return an owned annex');
      }
      return result.conversation;
    },
    [owned, ownerId, postCreate]
  );

  const rename = useCallback(
    async (row: ConversationSummary, title: string) => {
      if (row.user_id !== ownerId || row.kind !== 'secondary' || row.title === null) {
        throw new Error('Invalid discussion title target');
      }
      const request = { title, expected_title: row.title, expected_revision: row.revision };
      const updated = await owned(signal =>
        patchTitle(`/conversations/${encodeURIComponent(row.id)}`, request, { signal })
      );
      if (
        !updated ||
        updated.id !== row.id ||
        updated.revision !== row.revision ||
        updated.user_id !== ownerId
      ) {
        throw new Error('Discussion rename did not return the reviewed annex');
      }
      return updated;
    },
    [owned, ownerId, patchTitle]
  );

  const retire = useCallback(
    async (target: ConversationSummary, action: ConversationOperation, operationId: string) => {
      if (target.user_id !== ownerId || (action === 'delete' && target.kind !== 'secondary')) {
        throw new Error('Invalid discussion lifecycle target');
      }
      const endpoint = `/conversations/${encodeURIComponent(target.id)}`;
      const request = { operation_id: operationId, expected_revision: target.revision };
      const result = await owned(async signal => {
        try {
          return action === 'reset'
            ? await postReset(`${endpoint}/reset`, request, { signal })
            : await deleteRow(endpoint, request, { signal });
        } catch (error) {
          const status = getApiErrorStatus(error);
          if (signal.aborted || (status && status >= 400 && status < 500)) throw error;
          // An unknown reply may hide a committed effect. Read the receipt before
          // showing a failure. Any explicit retry keeps the same operation id.
          return apiClient
            .get<ConversationOperationResult>(`/conversations/operations/${operationId}`, {
              signal,
            })
            .catch(() => {
              throw error;
            });
        }
      });
      if (!matchesOperation(result, target, action, operationId)) {
        throw new Error('Discussion lifecycle receipt did not confirm the reviewed act');
      }
      return result;
    },
    [owned, ownerId, postReset, deleteRow]
  );

  return { create, rename, retire };
}

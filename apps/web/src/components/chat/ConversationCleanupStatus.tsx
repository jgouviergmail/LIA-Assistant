'use client';

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import type { ConversationOperationResult } from '@/types/conversation';

const STATUS_REFRESH_MS = 15_000;

/** Cleanup progress describes the durable receipt, independently of the selected chat. */
export function ConversationCleanupStatus({
  receipt,
  onComplete,
}: {
  receipt: ConversationOperationResult;
  onComplete: (id: string) => void;
}) {
  const { t } = useTranslation();
  const endpoint = `/conversations/operations/${encodeURIComponent(receipt.operation_id)}`;
  const { data, refetch, acceptData, error } = useApiQuery<ConversationOperationResult>(endpoint, {
    componentName: 'ConversationCleanup',
    initialData: receipt,
    onSuccess: result => {
      if (result.cleanup_complete) onComplete(receipt.operation_id);
    },
  });
  const { mutate: retry, loading } = useApiMutation<undefined, ConversationOperationResult>({
    method: 'POST',
    componentName: 'ConversationCleanupRetry',
    retainResponse: false,
  });
  const [retryFailed, setRetryFailed] = useState(false);
  const needsAttention = data?.state === 'needs_attention';
  useEffect(() => {
    if (needsAttention) return;
    const poll = () => {
      if (document.visibilityState === 'visible') void refetch();
    };
    const timer = window.setInterval(poll, STATUS_REFRESH_MS);
    document.addEventListener('visibilitychange', poll);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', poll);
    };
  }, [needsAttention, refetch]);

  async function retryCleanup() {
    setRetryFailed(false);
    try {
      const result = await retry(`${endpoint}/retry`);
      if (result) acceptData(result);
    } catch {
      setRetryFailed(true);
    }
  }

  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-center gap-2 border-b bg-card px-3 py-2 text-sm"
    >
      <span>
        {t(
          error || retryFailed
            ? 'chat.discussions.cleanup_read_error'
            : needsAttention
              ? 'chat.discussions.cleanup_failed'
              : 'chat.discussions.cleanup_pending'
        )}
      </span>
      {needsAttention && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          isLoading={loading}
          onClick={() => void retryCleanup()}
        >
          {t('chat.discussions.cleanup_retry')}
        </Button>
      )}
      {error && (
        <Button type="button" size="sm" variant="outline" onClick={() => void refetch()}>
          {t('common.retry')}
        </Button>
      )}
    </div>
  );
}

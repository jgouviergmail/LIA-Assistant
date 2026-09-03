/**
 * Hooks for the Gmail label sources of a RAG space (ADR-262).
 *
 * - useMailSources: link, unlink and sync mutations (the sources themselves
 *   come from the space detail the parent page loads, like the Drive ones);
 * - useGmailLabels: the labels the picker offers, fetched on demand.
 *
 * Follows the useDriveSources pattern: useApiMutation + apiClient.
 */

'use client';

import { useCallback, useEffect, useState } from 'react';

import apiClient from '@/lib/api-client';
import type { GmailLabel, RAGMailSource } from '@/types/rag-spaces';

import { useApiMutation } from './useApiMutation';

/** Link / unlink / sync mutations for one space's mail sources. */
export function useMailSources(spaceId: string) {
  const linkMutation = useApiMutation<{ label_id: string; label_name: string }, RAGMailSource>({
    method: 'POST',
    componentName: 'MailSources',
  });

  const unlinkMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'MailSources',
  });

  const syncMutation = useApiMutation<void, { sync_status: string }>({
    method: 'POST',
    componentName: 'MailSources',
  });

  const linkLabel = useCallback(
    async (labelId: string, labelName: string) =>
      linkMutation.mutate(`/rag-spaces/${spaceId}/mail-sources`, {
        label_id: labelId,
        label_name: labelName,
      }),
    [spaceId, linkMutation]
  );

  const unlinkLabel = useCallback(
    async (sourceId: string, deleteDocuments = false) =>
      unlinkMutation.mutate(
        `/rag-spaces/${spaceId}/mail-sources/${sourceId}?delete_documents=${deleteDocuments}`
      ),
    [spaceId, unlinkMutation]
  );

  const syncLabel = useCallback(
    async (sourceId: string) =>
      syncMutation.mutate(`/rag-spaces/${spaceId}/mail-sources/${sourceId}/sync`),
    [spaceId, syncMutation]
  );

  return {
    linkLabel,
    unlinkLabel,
    syncLabel,
    linking: linkMutation.loading,
    unlinking: unlinkMutation.loading,
    syncing: syncMutation.loading,
  };
}

/**
 * The user's own Gmail labels, fetched when the picker opens.
 *
 * `enabled` keeps the request off the page's critical path: a closed picker
 * asks Gmail nothing.
 */
export function useGmailLabels(spaceId: string, enabled: boolean) {
  const [labels, setLabels] = useState<GmailLabel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchLabels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<GmailLabel[]>(`/rag-spaces/${spaceId}/mail-labels`);
      setLabels(data ?? []);
    } catch {
      setError('failed');
      setLabels([]);
    } finally {
      setLoading(false);
    }
  }, [spaceId]);

  useEffect(() => {
    if (enabled) {
      fetchLabels();
    }
  }, [enabled, fetchLabels]);

  return { labels, loading, error, refetch: fetchLabels };
}

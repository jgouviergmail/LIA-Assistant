/**
 * Hook for RAG Spaces CRUD operations.
 *
 * Account-owned queries and resource refresh share the native application boundary.
 * Mutations retain source optimistic updates and reject retired account callbacks.
 *
 * Phase: evolution — RAG Spaces (User Knowledge Documents)
 * Created: 2026-03-14
 */

import { useCallback, useState } from 'react';
import { publishApplicationResources } from '@/lib/application-resources';
import { useApplicationAccountQuery } from './useApplicationAccountQuery';
import { useApplicationResourceSync } from './useApplicationResourceSync';
import { useApiMutation } from './useApiMutation';
import type {
  RAGSpace,
  RAGSpaceDetail,
  RAGSpaceListResponse,
  RAGSpaceCreatePayload,
  RAGSpaceUpdatePayload,
  RAGSpaceToggleResponse,
  SpaceListQuery,
} from '@/types/rag-spaces';

const ENDPOINT = '/rag-spaces';
const releaseSpaceOverride = () => {};

/**
 * Hook for managing RAG Spaces (list, create, update, delete, toggle).
 */
export function useSpaces(criteria?: SpaceListQuery) {
  const queryKey = JSON.stringify(criteria) ?? '';
  const [acceptedQuery, setAcceptedQuery] = useState('');
  const acceptQuery = useCallback(() => setAcceptedQuery(queryKey), [queryKey]);
  const {
    data: receivedData,
    loading,
    error,
    refetch,
    setData,
    ownerId,
    isCurrent,
  } = useApplicationAccountQuery<RAGSpaceListResponse>(ENDPOINT, 'Spaces', true, acceptQuery, {
    params: criteria ? { ...criteria } : undefined,
  });
  const listData = acceptedQuery === queryKey ? receivedData : undefined;
  useApplicationResourceSync(ownerId, 'spaces', refetch, releaseSpaceOverride);

  const refreshFiltered = useCallback(() => {
    if (!criteria || !ownerId) return false;
    publishApplicationResources(ownerId, new Set(['spaces']));
    return true;
  }, [criteria, ownerId]);

  const spaces = listData?.spaces ?? [];
  const total = listData?.total ?? 0;
  const activeCount = spaces.filter(s => s.is_active).length;

  // Mutations
  const createMutation = useApiMutation<RAGSpaceCreatePayload, RAGSpace>({
    method: 'POST',
    componentName: 'Spaces',
  });

  const updateMutation = useApiMutation<RAGSpaceUpdatePayload, RAGSpace>({
    method: 'PATCH',
    componentName: 'Spaces',
  });

  const deleteMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'Spaces',
  });

  const toggleMutation = useApiMutation<void, RAGSpaceToggleResponse>({
    method: 'PATCH',
    componentName: 'Spaces',
  });

  const createSpace = useCallback(
    async (payload: RAGSpaceCreatePayload) => {
      if (!isCurrent()) return;
      const result = await createMutation.mutate(ENDPOINT, payload);
      if (!isCurrent()) return;
      if (result) {
        if (refreshFiltered()) return result;
        // Optimistic: add to list
        setData(prev => {
          if (!prev) return prev;
          const newSpace: RAGSpace = {
            ...result,
            document_count: 0,
            ready_document_count: 0,
            total_size: 0,
          };
          return {
            spaces: [...prev.spaces, newSpace],
            total: prev.total + 1,
          };
        });
      }
      return result;
    },
    [createMutation, setData, isCurrent, refreshFiltered]
  );

  const updateSpace = useCallback(
    async (spaceId: string, payload: RAGSpaceUpdatePayload) => {
      if (!isCurrent()) return;
      const result = await updateMutation.mutate(`${ENDPOINT}/${spaceId}`, payload);
      if (!isCurrent()) return;
      if (result) {
        if (refreshFiltered()) return result;
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            spaces: prev.spaces.map(s =>
              s.id === spaceId
                ? {
                    ...s,
                    name: result.name,
                    description: result.description,
                    is_favorite: result.is_favorite,
                  }
                : s
            ),
          };
        });
      }
      return result;
    },
    [updateMutation, setData, isCurrent, refreshFiltered]
  );

  const deleteSpace = useCallback(
    async (spaceId: string) => {
      if (!isCurrent()) return;
      // Mutation throws on failure — only update UI on success
      await deleteMutation.mutate(`${ENDPOINT}/${spaceId}`);
      if (!isCurrent()) return;
      if (refreshFiltered()) return;
      setData(prev => {
        if (!prev) return prev;
        return {
          spaces: prev.spaces.filter(s => s.id !== spaceId),
          total: prev.total - 1,
        };
      });
    },
    [deleteMutation, setData, isCurrent, refreshFiltered]
  );

  const toggleSpace = useCallback(
    async (spaceId: string) => {
      if (!isCurrent()) return;
      const result = await toggleMutation.mutate(`${ENDPOINT}/${spaceId}/toggle`);
      if (!isCurrent()) return;
      if (result) {
        if (refreshFiltered()) return result;
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            spaces: prev.spaces.map(s =>
              s.id === spaceId ? { ...s, is_active: result.is_active } : s
            ),
          };
        });
      }
      return result;
    },
    [toggleMutation, setData, isCurrent, refreshFiltered]
  );

  return {
    // Data
    spaces,
    total,
    activeCount,
    loading: !!ownerId && !error && (loading || listData === undefined),
    error,
    refetch,

    // Mutations
    createSpace,
    updateSpace,
    deleteSpace,
    toggleSpace,

    // Mutation states
    creating: createMutation.loading,
    updating: updateMutation.loading,
    deleting: deleteMutation.loading,
    toggling: toggleMutation.loading,
  };
}

/**
 * Hook for fetching a single space detail (with documents).
 */
export function useSpaceDetail(spaceId: string | null) {
  const { data, loading, error, refetch, setData, ownerId } =
    useApplicationAccountQuery<RAGSpaceDetail>(
      spaceId ? `${ENDPOINT}/${spaceId}` : '',
      'SpaceDetail',
      !!spaceId
    );
  useApplicationResourceSync(
    spaceId ? ownerId : undefined,
    'spaces',
    refetch,
    releaseSpaceOverride
  );

  return { space: data?.id === spaceId ? data : null, loading, error, refetch, setData };
}

/**
 * Hook for fetching active spaces count (lightweight, for chat indicator).
 */
export function useActiveSpaces() {
  const {
    data: listData,
    loading,
    refetch,
    ownerId,
  } = useApplicationAccountQuery<RAGSpaceListResponse>(ENDPOINT, 'ActiveSpaces');
  useApplicationResourceSync(ownerId, 'spaces', refetch, releaseSpaceOverride);

  const activeSpaces = (listData?.spaces ?? []).filter(s => s.is_active);

  return { activeSpaces, activeCount: activeSpaces.length, loading };
}

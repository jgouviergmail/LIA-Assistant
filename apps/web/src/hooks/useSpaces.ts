/**
 * Hook for RAG Spaces CRUD operations.
 *
 * Follows the useSkills pattern: useApiQuery + useApiMutation + optimistic updates.
 *
 * Phase: evolution — RAG Spaces (User Knowledge Documents)
 * Created: 2026-03-14
 */

import { useCallback } from 'react';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';
import type {
  RAGSpace,
  RAGSpaceDetail,
  RAGSpaceListResponse,
  RAGSpaceCreatePayload,
  RAGSpaceUpdatePayload,
  RAGSpaceToggleResponse,
} from '@/types/rag-spaces';

const ENDPOINT = '/rag-spaces';

/**
 * Hook for managing RAG Spaces (list, create, update, delete, toggle).
 */
export function useSpaces() {
  const {
    data: listData,
    loading,
    error,
    refetch,
    setData,
  } = useApiQuery<RAGSpaceListResponse>(ENDPOINT, {
    componentName: 'Spaces',
    initialData: { spaces: [], total: 0 },
  });

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
      const result = await createMutation.mutate(ENDPOINT, payload);
      if (result) {
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
    [createMutation, setData]
  );

  const updateSpace = useCallback(
    async (spaceId: string, payload: RAGSpaceUpdatePayload) => {
      const result = await updateMutation.mutate(`${ENDPOINT}/${spaceId}`, payload);
      if (result) {
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            spaces: prev.spaces.map(s =>
              s.id === spaceId ? { ...s, name: result.name, description: result.description } : s
            ),
          };
        });
      }
      return result;
    },
    [updateMutation, setData]
  );

  const deleteSpace = useCallback(
    async (spaceId: string) => {
      // Mutation throws on failure — only update UI on success
      await deleteMutation.mutate(`${ENDPOINT}/${spaceId}`);
      setData(prev => {
        if (!prev) return prev;
        return {
          spaces: prev.spaces.filter(s => s.id !== spaceId),
          total: prev.total - 1,
        };
      });
    },
    [deleteMutation, setData]
  );

  const toggleSpace = useCallback(
    async (spaceId: string) => {
      const result = await toggleMutation.mutate(`${ENDPOINT}/${spaceId}/toggle`);
      if (result) {
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
    [toggleMutation, setData]
  );

  return {
    // Data
    spaces,
    total,
    activeCount,
    loading,
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
  const { data, loading, error, refetch, setData } = useApiQuery<RAGSpaceDetail>(
    spaceId ? `${ENDPOINT}/${spaceId}` : '',
    {
      componentName: 'SpaceDetail',
      enabled: !!spaceId,
    }
  );

  return { space: data ?? null, loading, error, refetch, setData };
}

/**
 * Hook for fetching active spaces count (lightweight, for chat indicator).
 */
export function useActiveSpaces() {
  const { data: listData, loading } = useApiQuery<RAGSpaceListResponse>(ENDPOINT, {
    componentName: 'ActiveSpaces',
    initialData: { spaces: [], total: 0 },
  });

  const activeSpaces = (listData?.spaces ?? []).filter(s => s.is_active);

  return { activeSpaces, activeCount: activeSpaces.length, loading };
}

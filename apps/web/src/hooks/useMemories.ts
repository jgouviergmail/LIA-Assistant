import { useState, useCallback } from 'react';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';

/**
 * Memory category types matching backend schema.
 */
export type MemoryCategory =
  | 'preference'
  | 'personal'
  | 'relationship'
  | 'event'
  | 'pattern'
  | 'sensitivity';

/**
 * Memory item from the API.
 */
export interface Memory {
  id: string;
  content: string;
  category: MemoryCategory;
  emotional_weight: number;
  trigger_topic: string;
  usage_nuance: string;
  importance: number;
  created_at?: string;
  updated_at?: string;
  // Phase 6: Purge tracking fields
  pinned?: boolean;
  usage_count?: number;
  last_accessed_at?: string;
}

/**
 * Memory creation payload.
 */
export interface MemoryCreate {
  content: string;
  category: MemoryCategory;
  emotional_weight?: number;
  trigger_topic?: string;
  usage_nuance?: string;
  importance?: number;
}

/**
 * Memory update payload.
 */
export interface MemoryUpdate {
  content?: string;
  category?: MemoryCategory;
  emotional_weight?: number;
  trigger_topic?: string;
  usage_nuance?: string;
  importance?: number;
}

/**
 * Memory list response from API.
 */
export interface MemoryListResponse {
  items: Memory[];
  total: number;
  by_category: Record<string, number>;
}

/**
 * Category info for UI display.
 */
export interface MemoryCategoryInfo {
  name: string;
  label: string;
  description: string;
  icon: string;
}

/**
 * Get emoji indicator for emotional weight.
 */
export function getEmotionalEmoji(weight: number): string {
  if (weight <= -7) return '🔴'; // Trauma/deep pain
  if (weight <= -3) return '🟠'; // Negative moderate
  if (weight >= 7) return '💚'; // Very positive
  if (weight >= 3) return '🟢'; // Positive
  return '⚪'; // Neutral
}

/**
 * Get emotional state label.
 */
export function getEmotionalLabel(weight: number): string {
  if (weight <= -7) return 'Zone sensible';
  if (weight <= -3) return 'Négatif';
  if (weight >= 7) return 'Très positif';
  if (weight >= 3) return 'Positif';
  return 'Neutre';
}

/**
 * Hook for managing user memories.
 * Uses optimistic updates to prevent focus loss during mutations.
 */
export function useMemories() {
  const [categoryFilter, setCategoryFilter] = useState<MemoryCategory | null>(null);

  // Fetch memories
  const {
    data: memoriesData,
    loading,
    error,
    refetch,
    setData,
  } = useApiQuery<MemoryListResponse>('/memories', {
    componentName: 'useMemories',
    initialData: { items: [], total: 0, by_category: {} },
    params: categoryFilter ? { category: categoryFilter } : undefined,
    deps: [categoryFilter],
  });

  // Fetch categories
  const { data: categoriesData } = useApiQuery<{ categories: MemoryCategoryInfo[] }>(
    '/memories/categories',
    {
      componentName: 'useMemories',
      initialData: { categories: [] },
    }
  );

  // Create mutation
  const { mutate: createMutate, loading: creating } = useApiMutation<MemoryCreate, Memory>({
    method: 'POST',
    componentName: 'useMemories',
  });

  // Delete mutation
  const { mutate: deleteMutate, loading: deleting } = useApiMutation({
    method: 'DELETE',
    componentName: 'useMemories',
  });

  // Update mutation
  const { mutate: updateMutate, loading: updating } = useApiMutation({
    method: 'PATCH',
    componentName: 'useMemories',
  });

  // Delete all mutation
  const { mutate: deleteAllMutate, loading: deletingAll } = useApiMutation({
    method: 'DELETE',
    componentName: 'useMemories',
  });

  /**
   * Helper to recalculate byCategory counts from items list.
   */
  const recalculateByCategory = useCallback((items: Memory[]): Record<string, number> => {
    const counts: Record<string, number> = {};
    for (const item of items) {
      counts[item.category] = (counts[item.category] || 0) + 1;
    }
    return counts;
  }, []);

  /**
   * Create a new memory (optimistic update).
   */
  const createMemory = useCallback(
    async (data: MemoryCreate): Promise<Memory | undefined> => {
      const result = await createMutate('/memories', data);

      if (result) {
        // Optimistic update: add the new memory to local state
        setData((prev) => {
          if (!prev) return prev;
          const newItems = [result, ...prev.items];
          return {
            ...prev,
            items: newItems,
            total: prev.total + 1,
            by_category: recalculateByCategory(newItems),
          };
        });
      }

      return result;
    },
    [createMutate, setData, recalculateByCategory]
  );

  /**
   * Delete a memory (optimistic update).
   */
  const deleteMemory = useCallback(
    async (memoryId: string) => {
      await deleteMutate(`/memories/${memoryId}`);

      // Optimistic update: remove from local state
      setData((prev) => {
        if (!prev) return prev;
        const newItems = prev.items.filter((m) => m.id !== memoryId);
        return {
          ...prev,
          items: newItems,
          total: Math.max(0, prev.total - 1),
          by_category: recalculateByCategory(newItems),
        };
      });
    },
    [deleteMutate, setData, recalculateByCategory]
  );

  /**
   * Update a memory (optimistic update).
   */
  const updateMemory = useCallback(
    async (memoryId: string, data: MemoryUpdate) => {
      await updateMutate(`/memories/${memoryId}`, data);

      // Optimistic update: update in local state
      setData((prev) => {
        if (!prev) return prev;
        const newItems = prev.items.map((m) =>
          m.id === memoryId ? { ...m, ...data, updated_at: new Date().toISOString() } : m
        );
        return {
          ...prev,
          items: newItems,
          by_category: recalculateByCategory(newItems),
        };
      });
    },
    [updateMutate, setData, recalculateByCategory]
  );

  /**
   * Delete all memories (optimistic update).
   */
  const deleteAllMemories = useCallback(
    async (preservePinned: boolean = false) => {
      const url = preservePinned ? '/memories?preserve_pinned=true' : '/memories';
      await deleteAllMutate(url);

      // Optimistic update: clear or keep only pinned
      setData((prev) => {
        if (!prev) return prev;
        const newItems = preservePinned ? prev.items.filter((m) => m.pinned) : [];
        return {
          ...prev,
          items: newItems,
          total: newItems.length,
          by_category: recalculateByCategory(newItems),
        };
      });
    },
    [deleteAllMutate, setData, recalculateByCategory]
  );

  /**
   * Toggle pin state (optimistic update).
   */
  const togglePin = useCallback(
    async (memoryId: string, pinned: boolean) => {
      await updateMutate(`/memories/${memoryId}/pin`, { pinned });

      // Optimistic update: toggle pin in local state
      setData((prev) => {
        if (!prev) return prev;
        const newItems = prev.items.map((m) => (m.id === memoryId ? { ...m, pinned } : m));
        return {
          ...prev,
          items: newItems,
        };
      });
    },
    [updateMutate, setData]
  );

  return {
    memories: memoriesData?.items ?? [],
    total: memoriesData?.total ?? 0,
    byCategory: memoriesData?.by_category ?? {},
    categories: categoriesData?.categories ?? [],
    loading,
    error,
    creating,
    deleting,
    updating,
    deletingAll,
    categoryFilter,
    setCategoryFilter,
    refetch,
    createMemory,
    deleteMemory,
    updateMemory,
    deleteAllMemories,
    togglePin,
  };
}

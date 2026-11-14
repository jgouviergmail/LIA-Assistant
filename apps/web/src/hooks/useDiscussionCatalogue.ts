'use client';

import { useCallback, useState } from 'react';
import { useApiQuery } from '@/hooks/useApiQuery';
import type {
  ConversationCatalogueConfig,
  ConversationCataloguePage,
  ConversationSummary,
} from '@/types/conversation';

/** Fetch only the catalogue page being browsed, keeping the last visible page on error. */
export function useDiscussionCatalogue(config: ConversationCatalogueConfig | undefined) {
  const [offset, setOffset] = useState(0);
  const [retired, setRetired] = useState<ReadonlySet<string>>(() => new Set());
  const { data, loading, error, refetch, setData } = useApiQuery<ConversationCataloguePage>(
    '/conversations',
    {
      componentName: 'DiscussionCatalogue',
      enabled: config !== undefined,
      params: { offset },
    }
  );
  const remove = useCallback((id: string) => setRetired(previous => new Set(previous).add(id)), []);
  const rename = useCallback(
    (row: ConversationSummary) => {
      setData(
        previous =>
          previous && {
            ...previous,
            items: previous.items.map(item =>
              item.id === row.id && item.revision === row.revision ? row : item
            ),
          }
      );
    },
    [setData]
  );
  const visibleItems = data?.items.filter(row => !retired.has(row.id));
  // Keep count/pagination from an actual server snapshot. A local acknowledgement
  // can remove a row immediately, but cannot invent a new aggregate.
  const needsRecount = visibleItems?.length !== data?.items.length;
  return {
    page: data,
    visibleItems,
    needsRecount,
    loading,
    error: Boolean(error),
    refetch,
    setOffset,
    remove,
    rename,
  };
}

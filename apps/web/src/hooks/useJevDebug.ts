import { useEffect } from 'react';
import { useApiQuery, type UseApiQueryResult } from './useApiQuery';
import type { JevTracePage } from '@/types/jev';

/** Mounted only while the debug section is open; closing aborts and forgets it. */
export function useJevDebug(): UseApiQueryResult<JevTracePage> {
  const query: UseApiQueryResult<JevTracePage> = useApiQuery<JevTracePage>('/debug/jev', {
    componentName: 'JevDebug',
    // A revoked permission or unavailable feed must not leave private data on screen.
    onError: () => query.setData(undefined),
  });
  const { loading, refetch } = query;
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!loading && document.visibilityState === 'visible') void refetch();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [loading, refetch]);
  return query;
}

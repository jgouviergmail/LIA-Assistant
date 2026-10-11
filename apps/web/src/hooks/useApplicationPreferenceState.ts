'use client';

import { useCallback, useRef, useState } from 'react';
import { publishApplicationResources, type ApplicationResource } from '@/lib/application-resources';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';

/** Keep optimistic list edits until the last write and an authenticated reread finish. */
export function useApplicationPreferenceState<T>(
  ownerId: string | undefined,
  saved: T | undefined,
  resource: ApplicationResource,
  refetch: () => Promise<void>,
  write: (value: T) => Promise<unknown>
) {
  const { lifetime, isCurrent } = useApplicationAccountLifetime(ownerId);
  const [override, setOverride] = useState<{ lifetime: typeof lifetime; value: T } | null>(null);
  const writes = useRef(new Map<typeof lifetime, number>());
  const revisions = useRef(new Map<typeof lifetime, number>());
  const value = override?.lifetime === lifetime ? override.value : saved;
  const release = useCallback(() => {
    setOverride(current =>
      current && (writes.current.get(current.lifetime) ?? 0) > 0 ? current : null
    );
  }, []);
  useApplicationResourceSync(ownerId, resource, refetch, release);
  const save = useCallback(
    async (next: T): Promise<boolean> => {
      if (!ownerId || !isCurrent()) return false;
      const previous = value;
      const revision = (revisions.current.get(lifetime) ?? 0) + 1;
      revisions.current.set(lifetime, revision);
      writes.current.set(lifetime, (writes.current.get(lifetime) ?? 0) + 1);
      setOverride({ lifetime, value: next });
      try {
        await write(next);
        return true;
      } catch {
        if (revisions.current.get(lifetime) === revision) {
          setOverride(current => {
            if (current?.lifetime !== lifetime) return current;
            return previous === undefined ? null : { lifetime, value: previous };
          });
        }
        return false;
      } finally {
        const remaining = (writes.current.get(lifetime) ?? 1) - 1;
        if (remaining > 0) writes.current.set(lifetime, remaining);
        else {
          writes.current.delete(lifetime);
          revisions.current.delete(lifetime);
        }
        publishApplicationResources(ownerId, new Set([resource]));
      }
    },
    [ownerId, lifetime, isCurrent, value, resource, write]
  );
  return { value, save };
}

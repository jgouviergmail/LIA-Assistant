'use client';

import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { subscribeApplicationResource, type ApplicationResource } from '@/lib/application-resources';

const nothingToRelease = () => {};

/** The query lifetime cancels obsolete reads; release overrides after rereading. */
export function useApplicationResourceSync(
  ownerId: string | undefined, resource: ApplicationResource,
  refetch: () => Promise<void>, releaseOverride: () => void = nothingToRelease,
) {
  const { t } = useTranslation();
  useEffect(() => {
    if (!ownerId) return;
    let cancelled = false;
    let running = false;
    let dirty = false;
    const read = async () => {
      if (running) { dirty = true; return; }
      running = true;
      try {
        do {
          dirty = false;
          await refetch();
          if (cancelled) return;
          if (!dirty) releaseOverride();
        } while (dirty);
      } catch {
        if (!cancelled) toast.error(t('settings.application_tools.sync_failed'));
      } finally { running = false; }
    };
    const unsubscribe = subscribeApplicationResource(ownerId, resource, () => { void read(); });
    return () => { cancelled = true; unsubscribe(); };
  }, [ownerId, resource, refetch, releaseOverride, t]);
}

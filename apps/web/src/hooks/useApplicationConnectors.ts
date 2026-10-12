'use client';

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useApplicationAccountQuery } from './useApplicationAccountQuery';
import { useApplicationAccountLifetime } from './useApplicationAccountLifetime';
import { useApplicationResourceSync } from './useApplicationResourceSync';
import type { ConnectorsResponse } from '@/components/settings/connectors/types';

/** A committed unlink rereads the database even when the list cache is unavailable. */
export function useApplicationConnectors() {
  const { t } = useTranslation();
  const query = useApplicationAccountQuery<ConnectorsResponse>(
    '/connectors?fresh=true',
    'UserConnectorsSection'
  );
  const { isCurrent } = useApplicationAccountLifetime(query.ownerId);
  const release = useCallback(() => {}, []);
  useApplicationResourceSync(query.ownerId, 'connectors', query.refetch, release);
  const verifiedRefetch = query.refetch;
  const refetch = useCallback(async () => {
    try {
      await verifiedRefetch();
    } catch {
      if (isCurrent()) toast.error(t('settings.application_tools.sync_failed'));
    }
  }, [verifiedRefetch, isCurrent, t]);
  return { ...query, refetch };
}

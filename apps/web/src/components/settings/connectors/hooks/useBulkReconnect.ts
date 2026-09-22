import { useRef, useState } from 'react';
import apiClient from '@/lib/api-client';
import { getApiErrorDetail } from '@/lib/api-error';
import { logger } from '@/lib/logger';
import { navigateToAuthorizationUrl } from '@/lib/safe-navigation';
import { toast } from 'sonner';
import type { Connector } from '../types';

export type OAuthProvider = 'google' | 'microsoft';

const PENDING_KEY = 'oauth_connectors_reconnect_pending';

export function useBulkReconnect(t: (key: string) => string) {
  const [dialogProvider, setDialogProvider] = useState<OAuthProvider | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  const submit = async (provider: OAuthProvider, types: string[]) => {
    if (inFlight.current || types.length === 0) return;
    inFlight.current = true;
    setBusy(true);
    try {
      const response = await apiClient.post<{ authorization_url: string }>(
        `/connectors/oauth-bulk/${provider}/authorize`,
        { connector_types: types }
      );
      try {
        sessionStorage.setItem(PENDING_KEY, 'true');
      } catch {
        // A restricted browser can still complete OAuth; callback URL carries the outcome.
      }
      navigateToAuthorizationUrl(response.authorization_url, 'bulk-reconnect');
    } catch (error) {
      logger.error('Failed to start grouped OAuth reconnection', error as Error, {
        component: 'useBulkReconnect', provider,
      });
      toast.error(getApiErrorDetail(error) ?? t('settings.connectors.bulk_reconnect.failed'));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const start = (provider: OAuthProvider, rows: Connector[]) => {
    const eligible = rows.filter(row => row.connector_type !== 'gmail');
    if (eligible.length === 0) return;
    const grantIds = new Set(eligible.map(row => row.oauth_grant_id).filter(Boolean));
    if (grantIds.size === 1 && eligible.every(row => row.oauth_grant_id)) {
      void submit(provider, eligible.map(row => row.connector_type));
    } else {
      setDialogProvider(provider);
    }
  };

  return { dialogProvider, setDialogProvider, busy, start, submit };
}

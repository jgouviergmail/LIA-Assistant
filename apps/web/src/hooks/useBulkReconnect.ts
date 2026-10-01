'use client';

/**
 * Starts one provider authorization for several expired services.
 *
 * Shared by « My connectors » and the health alert. The caller hands the
 * candidates the server marked as joinable (`lib/connectors/bulk-reconnect`);
 * when they all belong to ONE known account the consent starts at once, and
 * otherwise the account-choice dialog opens on exactly those candidates — the
 * hook keeps them, so a surface renders the dialog from here rather than
 * re-deriving a list that could differ.
 */

import { useRef, useState } from 'react';
import { toast } from 'sonner';

import apiClient from '@/lib/api-client';
import type { BulkProvider, BulkReconnectCandidate } from '@/lib/connectors/bulk-reconnect';
import { logger } from '@/lib/logger';
import { navigateToAuthorizationUrl } from '@/lib/safe-navigation';

const PENDING_KEY = 'oauth_connectors_reconnect_pending';

export interface BulkReconnectDialogState {
  provider: BulkProvider;
  candidates: BulkReconnectCandidate[];
}

export interface UseBulkReconnectOptions {
  /** Runs just before the browser leaves for the provider (e.g. a refetch marker). */
  onBeforeRedirect?: () => void;
}

export function useBulkReconnect(
  t: (key: string) => string,
  { onBeforeRedirect }: UseBulkReconnectOptions = {}
) {
  const [dialog, setDialog] = useState<BulkReconnectDialogState | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  const submit = async (provider: BulkProvider, types: string[]) => {
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
      onBeforeRedirect?.();
      navigateToAuthorizationUrl(response.authorization_url, 'bulk-reconnect');
    } catch (error) {
      // The refusal's detail is the server's technical English: logged, while
      // the person reads the translated sentence.
      logger.error('Failed to start grouped OAuth reconnection', error as Error, {
        component: 'useBulkReconnect',
        provider,
      });
      toast.error(t('settings.connectors.bulk_reconnect.failed'));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const start = (provider: BulkProvider, candidates: BulkReconnectCandidate[]) => {
    if (candidates.length === 0) return;
    const grantIds = new Set(candidates.map(candidate => candidate.oauth_grant_id));
    const oneKnownAccount = grantIds.size === 1 && !grantIds.has(null);
    if (oneKnownAccount) {
      void submit(
        provider,
        candidates.map(candidate => candidate.connector_type)
      );
    } else {
      setDialog({ provider, candidates });
    }
  };

  return { dialog, closeDialog: () => setDialog(null), busy, start, submit };
}

/** One provider authorization for all newly available Google or Microsoft services. */
import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { navigateToAuthorizationUrl } from '@/lib/safe-navigation';
import {
  GOOGLE_CONNECTOR_TYPES,
  GMAIL_TYPES,
  BULK_CONNECT_QUEUE_KEY,
  MICROSOFT_BULK_CONNECT_QUEUE_KEY,
  MICROSOFT_CONNECTOR_TYPES,
  MUTUAL_EXCLUSIVITY_MAP,
} from '../constants';
import { type Connector, isConnectorActive, isConnectorTypeExists } from '../types';

type Provider = 'google' | 'microsoft';
export interface KnownOAuthAccount { grantId: string; email: string | null }

interface UseBulkConnectOptions {
  connectors: Connector[];
  loading: boolean;
  t: (key: string) => string;
}

const PENDING_KEY = 'oauth_connectors_reconnect_pending';
const LEGACY_QUEUE_KEYS = [BULK_CONNECT_QUEUE_KEY, MICROSOFT_BULK_CONNECT_QUEUE_KEY];

export function availableTypes(provider: Provider, connectors: Connector[]): string[] {
  const types = provider === 'google'
    ? GOOGLE_CONNECTOR_TYPES.filter(type => type !== 'gmail')
    : MICROSOFT_CONNECTOR_TYPES;
  const activeTypes = new Set(
    connectors.filter(isConnectorActive).map(connector => connector.connector_type.toLowerCase())
  );
  return types.filter(type =>
    !isConnectorTypeExists(connectors, type, type === 'google_gmail' ? GMAIL_TYPES : undefined) &&
    !MUTUAL_EXCLUSIVITY_MAP[type]?.some(competing => activeTypes.has(competing))
  );
}

function knownAccounts(provider: Provider, connectors: Connector[]): KnownOAuthAccount[] {
  const types: readonly string[] = provider === 'google' ? GOOGLE_CONNECTOR_TYPES : MICROSOFT_CONNECTOR_TYPES;
  const accounts = new Map<string, KnownOAuthAccount>();
  for (const connector of connectors) {
    if (!types.includes(connector.connector_type) || !connector.oauth_grant_id) continue;
    const previous = accounts.get(connector.oauth_grant_id);
    accounts.set(connector.oauth_grant_id, {
      grantId: connector.oauth_grant_id,
      email: connector.metadata?.oauth_account_email ?? previous?.email ?? null,
    });
  }
  return [...accounts.values()];
}

export function useBulkConnect({ connectors, loading, t }: UseBulkConnectOptions) {
  const [bulkConnecting, setBulkConnecting] = useState(false);
  const [accountDialogProvider, setAccountDialogProvider] = useState<Provider | null>(null);
  const inFlight = useRef(false);
  const availableGoogleTypes = availableTypes('google', connectors);
  const availableMicrosoftTypes = availableTypes('microsoft', connectors);

  // A previous release persisted one queue per provider. It must never resume
  // after this one-request flow replaces the sequential OAuth journey.
  useEffect(() => {
    try { LEGACY_QUEUE_KEYS.forEach(key => localStorage.removeItem(key)); } catch { /* restricted storage */ }
  }, []);

  const authorize = async (provider: Provider, grantId: string | null): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBulkConnecting(true);
    try {
      const response = await apiClient.post<{ authorization_url: string }>(
        `/connectors/oauth-bulk/${provider}/connect-all/authorize`,
        grantId ? { grant_id: grantId } : {}
      );
      try { sessionStorage.setItem(PENDING_KEY, 'true'); } catch { /* restricted storage */ }
      setAccountDialogProvider(null);
      navigateToAuthorizationUrl(response.authorization_url, 'bulk-connect');
    } catch (error) {
      logger.error('Failed to start grouped connector authorization', error as Error, {
        component: 'useBulkConnect', provider,
      });
      toast.error(t(`settings.connectors.${provider}.connect_all_error`));
    } finally {
      inFlight.current = false;
      setBulkConnecting(false);
    }
  };

  const start = async (provider: Provider): Promise<void> => {
    if (loading || inFlight.current || accountDialogProvider) return;
    if (availableTypes(provider, connectors).length === 0) {
      toast.info(t(`settings.connectors.${provider}.all_already_connected`));
      return;
    }
    if (knownAccounts(provider, connectors).length > 0) {
      setAccountDialogProvider(provider);
      return;
    }
    await authorize(provider, null);
  };

  const confirmAccount = async (grantId: string | null): Promise<void> => {
    if (!accountDialogProvider) return;
    await authorize(accountDialogProvider, grantId);
  };

  return {
    bulkConnecting,
    canConnectGoogle: !loading && !bulkConnecting && availableGoogleTypes.length > 0,
    canConnectMicrosoft: !loading && !bulkConnecting && availableMicrosoftTypes.length > 0,
    accountDialogProvider,
    knownAccounts: accountDialogProvider ? knownAccounts(accountDialogProvider, connectors) : [],
    closeAccountDialog: () => setAccountDialogProvider(null),
    confirmAccount,
    connectAllGoogle: () => start('google'),
    connectAllMicrosoft: () => start('microsoft'),
  };
}

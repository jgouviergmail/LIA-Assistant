import { AlertTriangle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { ConnectorGroupTrigger } from './ConnectorGroupTrigger';
import { ErrorConnectorCard } from './ErrorConnectorCard';
import {
  bulkCandidates,
  type BulkProvider,
  type BulkReconnectCandidate,
} from '@/lib/connectors/bulk-reconnect';
import type { Connector } from './types';

interface Props {
  provider: BulkProvider;
  connectors: Connector[];
  busy: boolean;
  reconnectingConnector: string | null;
  onBulkReconnect: (candidates: BulkReconnectCandidate[]) => void;
  onReconnect: (connectorType: string) => void;
  t: (key: string) => string;
}

/** Keep provider-specific error actions beside the services they affect. */
export function OAuthErrorGroup({
  provider,
  connectors,
  busy,
  reconnectingConnector,
  onBulkReconnect,
  onReconnect,
  t,
}: Props) {
  if (connectors.length === 0) return null;
  // The server says which rows the grouped consent accepts (the legacy
  // `gmail` row is not one of them): the button never offers a refusal.
  const eligible = bulkCandidates(
    connectors,
    provider,
    connector => connector.metadata?.oauth_account_email
  );

  return (
    <AccordionItem value={`error-${provider}`} className="border rounded-lg px-3">
      <AccordionTrigger className="text-sm font-medium gap-2 hover:no-underline py-3">
        <ConnectorGroupTrigger
          state="error"
          label={t('settings.connectors.health.critical_title')}
          count={connectors.length}
          icon={AlertTriangle}
          t={t}
        />
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-2">
          {eligible.length > 0 && (
            <Button
              className="w-full sm:w-auto"
              disabled={busy}
              onClick={() => onBulkReconnect(eligible)}
            >
              {t(`settings.connectors.bulk_reconnect.${provider}_action`)}
            </Button>
          )}
          {connectors.map(connector => (
            <ErrorConnectorCard
              key={connector.id}
              connector={connector}
              t={t}
              reconnecting={reconnectingConnector === connector.connector_type}
              onReconnect={onReconnect}
            />
          ))}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}

'use client';

/**
 * The « Live » group of the connectors section (ADR-299; wave 2 A10): the
 * connected connectors with their disconnect, and — the category is ADDITIVE
 * — an available card for every provider the account has NOT set up, each
 * unfolding into its own form. Rendered ONLY when the instance publishes the
 * capability. Extracted so `UserConnectorsSection` (a frozen hotspot) grows
 * by two lines, not two accordion items.
 */

import { useState } from 'react';

import { AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { useAppConfig } from '@/hooks/useAppConfig';
import type { Language } from '@/i18n/settings';
import { LIVE_PROVIDERS, isLiveConnectorType } from '@/lib/live/providers';

import { AvailableConnectorCard } from './AvailableConnectorCard';
import { ConnectedConnectorCard } from './ConnectedConnectorCard';
import { ConnectorGroupTrigger } from './ConnectorGroupTrigger';
import { LiveConnectorForm } from './LiveConnectorForm';
import { isConnectorActive, type Connector } from './types';

export interface LiveConnectorGroupProps {
  connectors: Connector[];
  lng: Language;
  t: (key: string, options?: Record<string, string>) => string;
  /** Re-read the list after an activation. */
  refetch: () => void;
  /** Open the in-app disconnect confirmation for this connector id. */
  onDisconnect: (connectorId: string) => void;
}

export function LiveConnectorGroup({
  connectors,
  lng,
  t,
  refetch,
  onDisconnect,
}: LiveConnectorGroupProps) {
  const { config } = useAppConfig();
  const [formFor, setFormFor] = useState<string | null>(null);
  if (!config?.features?.live_enabled) return null;

  const activeTypes = new Set(
    connectors.filter(isConnectorActive).map(c => c.connector_type.toLowerCase())
  );
  const connected = connectors.filter(
    c => isConnectorActive(c) && isLiveConnectorType(c.connector_type)
  );
  const available = LIVE_PROVIDERS.filter(p => !activeTypes.has(p.connectorType));

  return (
    <>
      {connected.length > 0 && (
        <AccordionItem value="connected-live" className="border rounded-lg px-3">
          <AccordionTrigger className="text-sm font-medium gap-2 hover:no-underline py-3">
            <ConnectorGroupTrigger
              state="connected"
              label={t('settings.connectors.connected_live')}
              count={connected.length}
              glyph="🎙️"
              t={t}
            />
          </AccordionTrigger>
          <AccordionContent>
            <div className="space-y-3">
              {connected.map(connector => (
                <ConnectedConnectorCard
                  key={connector.id}
                  connector={connector}
                  lng={lng}
                  t={t}
                  deleteLoading={false}
                  onDisconnect={onDisconnect}
                />
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>
      )}
      {available.length > 0 && (
        <AccordionItem value="available-live" className="border rounded-lg px-3">
          <AccordionTrigger className="text-sm font-medium gap-2 hover:no-underline py-3">
            <ConnectorGroupTrigger
              state="available"
              label={t('settings.connectors.available_live')}
              count={available.length}
              glyph="🎙️"
              t={t}
            />
          </AccordionTrigger>
          <AccordionContent>
            <div className="space-y-3">
              {available.map(provider =>
                formFor === provider.id ? (
                  <LiveConnectorForm
                    key={provider.id}
                    lng={lng}
                    provider={provider.id}
                    onSuccess={() => {
                      setFormFor(null);
                      refetch();
                    }}
                    onCancel={() => setFormFor(null)}
                  />
                ) : (
                  <AvailableConnectorCard
                    key={provider.id}
                    connectorType={provider.connectorType}
                    label={t('settings.connectors.live.label', { brand: provider.label })}
                    description={t('settings.connectors.live.description', {
                      brand: provider.label,
                    })}
                    connectTitle={t('settings.connectors.live.connect')}
                    onConnect={() => setFormFor(provider.id)}
                  />
                )
              )}
            </div>
          </AccordionContent>
        </AccordionItem>
      )}
    </>
  );
}

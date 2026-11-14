'use client';

/**
 * The telephony group of the connectors section: the connected connector with
 * its disconnect, or one card that unfolds into the single-screen form.
 *
 * The operator's switch treats the two apart (ADR-280). Connecting a key is
 * an ACT of the capability — the wizard creates an agent at the vendor — and
 * is offered only where telephony is. A stored key is the person's RECORD: it
 * stays shown, with its removal, under the switch, as long as the deployment
 * mounts telephony at all (the API serves that one route outside the switch).
 *
 * Extracted from `UserConnectorsSection` (a frozen hotspot) like its Live
 * sibling: the group decides its own presence.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Phone } from '@/lib/icons';

import { AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { useAppConfig } from '@/hooks/useAppConfig';
import type { Language } from '@/i18n/settings';
import apiClient from '@/lib/api-client';
import { capabilityAvailable, capabilityMounted } from '@/lib/capability-availability';

import { AvailableConnectorCard } from './AvailableConnectorCard';
import { ConnectedConnectorCard } from './ConnectedConnectorCard';
import { ConnectorGroupTrigger } from './ConnectorGroupTrigger';
import { isTelephonyConnectorType } from './constants';
import { TelephonyConnectorForm } from './TelephonyConnectorForm';
import { isConnectorActive, type Connector } from './types';

export interface TelephonyConnectorGroupProps {
  connectors: Connector[];
  lng: Language;
  t: (key: string, options?: Record<string, string>) => string;
  /** Re-read the list after an activation or a disconnect. */
  refetch: () => void;
}

const ITEM = 'border rounded-lg bg-background [--lia-field-background:var(--color-card)] px-3';
const TRIGGER = 'text-sm font-medium gap-2 hover:no-underline py-3';

export function TelephonyConnectorGroup({
  connectors,
  lng,
  t,
  refetch,
}: TelephonyConnectorGroupProps) {
  const { config } = useAppConfig();
  const [showForm, setShowForm] = useState(false);

  const connected = connectors.filter(
    connector => isTelephonyConnectorType(connector.connector_type) && isConnectorActive(connector)
  );

  const disconnect = () => {
    // Telephony-specific: also deletes the LIA ElevenLabs agent.
    apiClient
      .delete('/telephony/connector')
      .then(() => refetch())
      .catch(() => toast.error(t('settings.connectors.disconnect_error')));
  };

  if (connected.length > 0) {
    // A stored key is the person's own RECORD: it stays removable under the
    // deployment flag, whatever the operator's switch says.
    if (!capabilityMounted(config, 'telephony')) return null;
    return (
      <AccordionItem value="connected-telephony" className={ITEM}>
        <AccordionTrigger className={TRIGGER}>
          <ConnectorGroupTrigger
            state="connected"
            label={t('settings.connectors.connected_telephony')}
            icon={Phone}
            count={connected.length}
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
                onDisconnect={disconnect}
              />
            ))}
            {/* The call history is NOT repeated here: it has its own
                deep-linkable section on this page (`TelephonyCallsSection`),
                which the in-call banner links to. */}
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  // Connecting creates an agent at the vendor: an ACT the switch closes.
  if (!capabilityAvailable(config, 'telephony')) return null;
  return (
    <AccordionItem value="available-telephony" className={ITEM}>
      <AccordionTrigger className={TRIGGER}>
        <ConnectorGroupTrigger
          state="available"
          label={t('settings.connectors.available_telephony')}
          icon={Phone}
          count={1}
          t={t}
        />
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {showForm ? (
            <TelephonyConnectorForm
              lng={lng}
              onSuccess={() => {
                setShowForm(false);
                refetch();
              }}
              onCancel={() => setShowForm(false)}
            />
          ) : (
            <AvailableConnectorCard
              connectorType="elevenlabs_telephony"
              label={t('settings.connectors.telephony.label')}
              description={t('settings.connectors.telephony.description')}
              connectTitle={t('settings.connectors.google.connect')}
              onConnect={() => setShowForm(true)}
            />
          )}
          {/* Past calls belong to the USER, not the connector: they stay in
              their own section (`TelephonyCallsSection`) after a disconnect. */}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}

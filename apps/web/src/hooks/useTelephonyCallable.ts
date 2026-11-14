'use client';

/**
 * Whether a call may be asked of LIA now (owner, 2026-11-07, D2).
 *
 * Two conditions, both read: the instance offers telephony (the operator's switch over the
 * deployment ceiling, `capabilities.telephony` of `/config`), and the account holds an ACTIVE
 * telephony connector (the connectors page's own predicate). An unknown configuration or an
 * unanswered read offers no call rather than one nothing could place. Relations and the contacts
 * tool read this one verdict.
 */
import { isTelephonyConnectorType } from '@/components/settings/connectors/constants';
import { isConnectorActive } from '@/components/settings/connectors/types';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useApplicationConnectors } from '@/hooks/useApplicationConnectors';
import { capabilityEnabled } from '@/lib/capability-state';

/** @returns Whether LIA can be asked to place a call for this account. */
export function useTelephonyCallable(): boolean {
  const { config } = useAppConfig();
  const { data } = useApplicationConnectors();
  if (!capabilityEnabled(config?.capabilities, 'telephony', false)) return false;
  return (data?.connectors ?? []).some(
    connector => isTelephonyConnectorType(connector.connector_type) && isConnectorActive(connector)
  );
}

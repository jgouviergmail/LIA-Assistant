/**
 * Connector types.
 * Extracted from UserConnectorsSection.tsx for DRY compliance.
 */

import { CONNECTOR_STATUS } from '@/constants/connectors';

export interface Connector {
  id: string;
  connector_type: string;
  status: string;
  created_at: string;
}

export interface ConnectorsResponse {
  connectors: Connector[];
}

export interface ConnectorPreferences {
  [key: string]: string;
}

export interface HomeLocation {
  address: string;
  lat: number;
  lon: number;
  place_id?: string | null;
}

/**
 * Check if a connector is active.
 */
export function isConnectorActive(connector: Connector): boolean {
  return connector.status.toLowerCase() === CONNECTOR_STATUS.ACTIVE;
}

/**
 * Check if a connector has error status (needs reconnection).
 */
export function isConnectorError(connector: Connector): boolean {
  return connector.status.toLowerCase() === CONNECTOR_STATUS.ERROR;
}

/**
 * Check if a connector type is connected (active) in the list.
 */
export function isConnectorTypeActive(
  connectors: Connector[],
  type: string,
  checkTypes?: readonly string[]
): boolean {
  const typesToCheck = checkTypes ?? [type];
  return connectors.some(
    c =>
      typesToCheck.includes(c.connector_type.toLowerCase()) &&
      c.status.toLowerCase() === CONNECTOR_STATUS.ACTIVE
  );
}

/**
 * Check if a connector type exists in the list (any status).
 * Used to determine if connector appears in "available" vs "error/connected" section.
 */
export function isConnectorTypeExists(
  connectors: Connector[],
  type: string,
  checkTypes?: readonly string[]
): boolean {
  const typesToCheck = checkTypes ?? [type];
  return connectors.some(c => typesToCheck.includes(c.connector_type.toLowerCase()));
}

/**
 * ErrorConnectorCard component.
 * Displays a connector with ERROR status, requiring reconnection.
 */

'use client';

import { Button } from '@/components/ui/button';
import { RefreshCw, AlertTriangle } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { ConnectorIcon } from './ConnectorIcon';
import { CONNECTOR_LABELS, isValidConnectorType } from '@/constants/connectors';
import type { Connector } from './types';

interface ErrorConnectorCardProps {
  connector: Connector;
  t: (key: string) => string;
  reconnecting: boolean;
  onReconnect: (connectorType: string) => void | Promise<void>;
}

function getConnectorLabel(type: string): string {
  // Handle legacy google_gmail -> gmail mapping
  const normalizedType = type === 'google_gmail' ? 'gmail' : type;
  if (isValidConnectorType(normalizedType)) {
    return CONNECTOR_LABELS[normalizedType];
  }
  // Fallback: format type as title case
  return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function ErrorConnectorCard({
  connector,
  t,
  reconnecting,
  onReconnect,
}: ErrorConnectorCardProps) {
  return (
    <div className="p-4 bg-destructive/10 rounded-lg border border-destructive/30">
      <div className="flex flex-col items-center gap-3">
        {/* Icon with error badge */}
        <div className="relative">
          <ConnectorIcon connectorType={connector.connector_type} />
          <div className="absolute -bottom-1 -right-1 bg-destructive rounded-full p-0.5">
            <AlertTriangle className="h-3 w-3 text-destructive-foreground" />
          </div>
        </div>

        {/* Connector name and status - centered */}
        <div className="text-center">
          <div className="font-medium">{getConnectorLabel(connector.connector_type)}</div>
          <div className="text-sm text-destructive">
            {t('settings.connectors.health.error_status')}
          </div>
        </div>

        {/* Reconnect button */}
        <Button
          variant="default"
          size="sm"
          onClick={() => onReconnect(connector.connector_type)}
          disabled={reconnecting}
          className="gap-2"
        >
          {reconnecting ? (
            <LoadingSpinner size="default" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          {t('settings.connectors.health.reconnect')}
        </Button>
      </div>
    </div>
  );
}

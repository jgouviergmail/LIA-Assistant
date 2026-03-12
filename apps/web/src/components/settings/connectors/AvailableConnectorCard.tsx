/**
 * AvailableConnectorCard component.
 * Displays an available (not connected) connector with connect button.
 * Supports mutual exclusivity blocking with warning message.
 */

'use client';

import { Button } from '@/components/ui/button';
import { Plug } from 'lucide-react';
import { ConnectorIcon } from './ConnectorIcon';

interface AvailableConnectorCardProps {
  connectorType: string;
  label: string;
  description: string;
  onConnect: () => void;
  connectTitle?: string;
  /** Whether this connector is blocked by mutual exclusivity */
  isBlocked?: boolean;
  /** Warning message when blocked (e.g., "Service blocked because X is active") */
  blockedMessage?: string;
}

export function AvailableConnectorCard({
  connectorType,
  label,
  description,
  onConnect,
  connectTitle,
  isBlocked = false,
  blockedMessage,
}: AvailableConnectorCardProps) {
  return (
    <div className="flex items-center justify-between p-4 border rounded-lg hover:bg-accent/50 transition-colors">
      <div className="flex items-center gap-3">
        <ConnectorIcon connectorType={connectorType} />
        <div>
          <div className="font-medium">{label}</div>
          <div className="text-sm text-muted-foreground">{description}</div>
          {isBlocked && blockedMessage && (
            <div className="text-xs text-amber-600 mt-0.5">{blockedMessage}</div>
          )}
        </div>
      </div>
      <Button
        variant="ghost"
        size="icon"
        onClick={onConnect}
        disabled={isBlocked}
        className="text-green-600 hover:text-green-700 hover:bg-green-500/10 dark:text-green-500 dark:hover:text-green-400"
        title={connectTitle}
      >
        <Plug className="h-4 w-4" />
      </Button>
    </div>
  );
}

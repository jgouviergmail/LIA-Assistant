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
    <div className="flex items-center justify-between gap-2 p-4 border rounded-lg hover:bg-accent/50 transition-colors">
      {/* min-w-0 lets the text column wrap INSIDE the row on narrow phones —
          without it the flex track inflates to the description's intrinsic
          width and silently overflows the viewport (same mechanism as the
          landing mobile-overflow defects). */}
      <div className="flex min-w-0 items-center gap-3">
        <span className="shrink-0">
          <ConnectorIcon connectorType={connectorType} />
        </span>
        <div className="min-w-0">
          <div className="font-medium break-words">{label}</div>
          <div className="text-sm text-muted-foreground break-words">{description}</div>
          {isBlocked && blockedMessage && (
            <div className="text-xs text-amber-600 mt-0.5 break-words">{blockedMessage}</div>
          )}
        </div>
      </div>
      <Button
        variant="ghost"
        size="icon"
        onClick={onConnect}
        disabled={isBlocked}
        className="shrink-0 text-green-600 hover:text-green-700 hover:bg-green-500/10 dark:text-green-500 dark:hover:text-green-400"
        title={connectTitle}
      >
        <Plug className="h-4 w-4" />
      </Button>
    </div>
  );
}

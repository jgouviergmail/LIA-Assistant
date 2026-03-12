/**
 * Component for displaying OAuth connector health alerts.
 *
 * SIMPLIFIED DESIGN:
 * - Only shows modal for CRITICAL issues (status=ERROR - refresh failed)
 * - NO warning toasts (proactive refresh handles normal expiration)
 * - Modal appears when a connector genuinely needs manual re-authentication
 *
 * Why this design:
 * - Proactive refresh job runs every 15 min, refreshes tokens 30 min before expiry
 * - access_token.expires_at in past is NORMAL - on-demand refresh gets new token
 * - Only status=ERROR means refresh failed and manual re-auth is needed
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import { AlertTriangle, ExternalLink } from 'lucide-react';
import { useConnectorHealth, ConnectorHealthItem } from '@/hooks/useConnectorHealth';
import { useAuth } from '@/hooks/useAuth';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import apiClient from '@/lib/api-client';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface ConnectorHealthAlertProps {
  lng: Language;
}

/**
 * Initiate OAuth reconnection flow.
 * Fetches the authorization URL from the API and redirects.
 */
async function initiateOAuthReconnect(authorizeUrl: string): Promise<void> {
  try {
    // authorizeUrl is like "/connectors/gmail/authorize"
    // We call it to get the actual Google authorization URL
    const response = await apiClient.get<{ authorization_url: string }>(authorizeUrl);
    window.location.href = response.authorization_url;
  } catch (error) {
    // If API call fails, show error toast
    console.error('Failed to initiate OAuth reconnect:', error);
    throw error;
  }
}

/**
 * Alert component for critical connector health issues.
 *
 * Only shows modal for connectors with status=ERROR (refresh failed).
 * Normal token expiration is handled silently by proactive refresh.
 */
export function ConnectorHealthAlert({ lng }: ConnectorHealthAlertProps) {
  const { t } = useTranslation(lng);
  const { user, isLoading: authLoading } = useAuth();
  const [showModal, setShowModal] = useState(false);
  const [modalConnectors, setModalConnectors] = useState<ConnectorHealthItem[]>([]);
  const [reconnecting, setReconnecting] = useState<string | null>(null);

  // Handle critical: Show modal
  const handleCritical = useCallback((connectors: ConnectorHealthItem[]) => {
    setModalConnectors(connectors);
    setShowModal(true);
  }, []);

  // Use the health check hook
  const { criticalConnectors, markReconnectPending } = useConnectorHealth({
    enabled: !authLoading,
    isAuthenticated: !!user,
    onCritical: handleCritical,
  });

  // Auto-close modal when all critical connectors are resolved
  useEffect(() => {
    if (showModal && criticalConnectors.length === 0) {
      setShowModal(false);
      setModalConnectors([]);
    }
  }, [showModal, criticalConnectors]);

  // Handle reconnect click (for modal buttons)
  const handleReconnect = async (connectorId: string, authorizeUrl: string) => {
    setReconnecting(connectorId);
    markReconnectPending();
    try {
      await initiateOAuthReconnect(authorizeUrl);
    } catch {
      toast.error(t('settings.connectors.health.reconnect_failed'));
      setReconnecting(null);
    }
  };

  // Get status text - simplified: only ERROR status triggers modal
  const getStatusText = (_connector: ConnectorHealthItem): string => {
    // With simplified design, all critical connectors have status=ERROR
    // This means token refresh failed and manual re-auth is required
    return t('settings.connectors.health.error_status');
  };

  return (
    <Dialog open={showModal} onOpenChange={setShowModal}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            {t('settings.connectors.health.modal_title')}
          </DialogTitle>
          <DialogDescription>{t('settings.connectors.health.modal_description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-4">
          {modalConnectors.map((connector) => (
            <div
              key={connector.id}
              className="flex flex-col gap-2 p-3 bg-destructive/10 rounded-lg border border-destructive/20"
            >
              <div className="flex items-center gap-2">
                <span className="text-destructive font-medium">{connector.display_name}</span>
                <span className="text-sm text-muted-foreground">- {getStatusText(connector)}</span>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="w-full"
                disabled={reconnecting === connector.id}
                onClick={() => handleReconnect(connector.id, connector.authorize_url)}
              >
                <ExternalLink className="h-4 w-4 mr-1" />
                {reconnecting === connector.id
                  ? t('settings.connectors.health.reconnecting')
                  : t('settings.connectors.health.reconnect')}
              </Button>
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setShowModal(false)}>
            {t('settings.connectors.health.dismiss')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

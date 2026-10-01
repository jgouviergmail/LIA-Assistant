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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { initiateOAuthReconnect } from '@/lib/connector-reconnect';
import { alertBulkGroups, type BulkGroup } from '@/lib/connectors/bulk-reconnect';
import { useBulkReconnect } from '@/hooks/useBulkReconnect';
import { BulkReconnectDialog } from './BulkReconnectDialog';
import { ConnectorHealthBanner } from './ConnectorHealthBanner';

/** Where a health item keeps its account address. */
const emailOf = (item: ConnectorHealthItem) => item.oauth_account_email;

interface ConnectorHealthAlertProps {
  lng: Language;
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
  // « Reconnect my Google services », as « My connectors » offers it, once two
  // joinable rows of one provider are down. The marker makes the health hook
  // refetch on return, exactly as a single reconnection does.
  const bulk = useBulkReconnect(t, { onBeforeRedirect: markReconnectPending });
  const startBulk = (group: BulkGroup) => {
    // An account choice opens its own dialog: never two stacked modals.
    setShowModal(false);
    bulk.start(group.provider, group.candidates);
  };
  const modalGroups = alertBulkGroups(modalConnectors, emailOf);

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
    <>
      {/* Persistent counterpart of the modal: the modal interrupts once, this
          stays for as long as the connector is broken. One hook instance
          feeds both — a second consumer would double the health polling. */}
      <ConnectorHealthBanner
        connectors={criticalConnectors}
        lng={lng}
        t={t}
        reconnecting={reconnecting !== null}
        onReconnect={handleReconnect}
        bulkGroups={alertBulkGroups(criticalConnectors, emailOf)}
        bulkBusy={bulk.busy}
        onBulkReconnect={startBulk}
      />
      {bulk.dialog && (
        <BulkReconnectDialog
          open
          onOpenChange={open => {
            if (!open) bulk.closeDialog();
          }}
          provider={bulk.dialog.provider}
          connectors={bulk.dialog.candidates}
          busy={bulk.busy}
          onSubmit={types => {
            if (bulk.dialog) void bulk.submit(bulk.dialog.provider, types);
          }}
          t={t}
        />
      )}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              {t('settings.connectors.health.modal_title')}
            </DialogTitle>
            <DialogDescription>
              {t('settings.connectors.health.modal_description')}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-4">
            {modalGroups.map(group => (
              <Button
                key={group.provider}
                className="w-full"
                aria-disabled={bulk.busy || undefined}
                onClick={() => {
                  if (!bulk.busy) startBulk(group);
                }}
              >
                {t(`settings.connectors.bulk_reconnect.${group.provider}_action`)}
              </Button>
            ))}
            {modalConnectors.map(connector => (
              <div
                key={connector.id}
                className="flex flex-col gap-2 p-3 bg-destructive/10 rounded-lg border border-destructive/20"
              >
                <div className="flex items-center gap-2">
                  <span className="text-destructive font-medium">{connector.display_name}</span>
                  <span className="text-sm text-muted-foreground">
                    - {getStatusText(connector)}
                  </span>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="w-full"
                  // Busy without `disabled` (the focus stays), and one redirect at
                  // a time: a second button must not start another meanwhile.
                  aria-disabled={reconnecting === connector.id || undefined}
                  onClick={() => {
                    if (reconnecting === null) {
                      void handleReconnect(connector.id, connector.authorize_url);
                    }
                  }}
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
    </>
  );
}
